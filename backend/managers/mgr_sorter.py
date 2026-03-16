from typing import List, Dict, Optional, Set, Tuple, Any
import heapq
from collections import deque, defaultdict
from backend.database.dao import ModDAO
from backend.managers.mgr_profile import ProfileContext
from backend.utils.logger import logger
from backend.settings import settings
from backend.managers.mgr_rules import RuleManager


class AtomicGroup:
    """原子组对象：联锁 Mod 的最小单位"""
    def __init__(self, mod_ids: List[str]):
        self.mod_ids = mod_ids  # 组内有序的 Mod ID 列表
        self.is_chain = len(mod_ids) > 1
        self.auto_activated = [] # 记录哪些是因联锁被强制补全的

    def __repr__(self):
        return f"<AtomicGroup chain={self.is_chain} ids={self.mod_ids}>"
class OrderSorter:
    # 定义规则权重：权重越高越难被打破
    # 级差设置大一些，防止多条低级规则累积压倒高级规则
    # 新版已经采用动态权重，这里保留旧版的权重定义，供参考
    # RULE_PRIORITIES = {
    #     'native': 10000,
    #     'community': 1000,
    #     'user': 100,
    #     'user_dynamic': 10,
    #     'unknown': 1
    # }
    def __init__(self, context: ProfileContext):
        self.context = context  # 环境上下文
        self.effective_rules_cache = {} # 缓存每个 Mod 的生效规则
        self.rule_mgr = RuleManager(context)

    def build_atomic_groups(self, active_ids: List[str]) -> List[AtomicGroup]:
        """
        第一步：将激活列表转化为原子组列表
        """
        # 1. 获取所有 Mod 的联锁数据
        # 注意：为了性能，一次性查出所有涉及到的 Mod 数据
        # 即使有的 Mod 不在 active_ids 里，只要它被联锁引用了，也要查
        all_mods_data = ModDAO.get_profile_mods(self.context)
        mod_map = {m['package_id'].lower(): m for m in all_mods_data}
        active_set = set(id.lower() for id in active_ids)
        visited = set()
        atomic_groups = []

        # 辅助函数：深度优先搜索构建链条
        def trace_chain(current_id: str, current_chain: List[str], auto_activated: List[str]):
            """
            递归构建一个 Mod 链条
            Args:
                current_id: 当前 Mod 的 ID
                current_chain: 当前链条的 Mod ID 列表
                auto_activated: 自动激活的 Mod ID 列表
            """
            if current_id in visited: return
            visited.add(current_id)
            # 如果当前 ID 不在激活列表中，记录为自动激活
            if current_id not in active_set:
                auto_activated.append(current_id)
            current_chain.append(current_id)
            mod_info = mod_map.get(current_id)
            if not mod_info: return
            # 寻找下一个
            next_id = mod_info.get('lock_next_mod')
            if next_id:
                next_id = next_id.lower()
                if next_id in mod_map and next_id not in visited:
                    # 检查回指逻辑：确保 B 的 previous 是 A，或者是 None
                    # 如果 B 的 previous 指向了别人，说明联锁数据矛盾
                    trace_chain(next_id, current_chain, auto_activated)
        
        # 2. 遍历所有激活项，从链条的“头”开始找起
        for mid in [id.lower() for id in active_ids]:
            if mid in visited:
                continue
            mod_info = mod_map.get(mid)
            if not mod_info:
                # 幽灵 Mod，单独成组
                atomic_groups.append(AtomicGroup([mid]))
                visited.add(mid)
                continue
            # 寻找链条的头部
            head_id = mid
            temp_visited = {head_id}
            while True:
                m_info = mod_map.get(head_id)
                prev_id = m_info.get('lock_previous_mod') if m_info else None
                if prev_id:
                    prev_id = prev_id.lower()
                    if prev_id in mod_map and prev_id not in temp_visited:
                        head_id = prev_id
                        temp_visited.add(head_id)
                    else: break
                else: break
            
            # 从头部开始构建完整链条
            chain = []
            auto_list = []
            trace_chain(head_id, chain, auto_list)
            group = AtomicGroup(chain)
            group.auto_activated = auto_list
            atomic_groups.append(group)

        return atomic_groups


    # =========================================================================
    # 加权图构建与循环消解
    # =========================================================================
    def get_rule_weight(self, source_type: str) -> int:
        """
        根据配置动态计算权重。
        配置列表越靠前 -> 索引越小 -> 权重越大
        """
        idx = self.rule_mgr.get_source_priority(source_type)
        # 基础权重 100，每高一级增加 1000。
        # 假设列表长度 4。Idx 0 (User) -> (5-0)*1000 = 5000
        # Idx 3 (Dynamic) -> (5-3)*1000 = 2000
        # 未知来源 -> 100
        if idx == 999: return 100
        return (10 - idx) * 1000 
    
    def _build_weighted_graph(self, groups: List[AtomicGroup], mod_map: Dict[str, dict], mod_to_group: Dict[str, AtomicGroup]):
        """
        构建带权重的依赖图，支持 Alternatives 备选连线和 is_force 绝对优先权
        返回: 
          adj: Dict[int, Dict[int, int]]  adj[u][v] = weight (表示 u 必须在 v 之前，权重 weight)
          edge_info: Dict[tuple, list] 记录每条边是由哪些具体规则生成的，用于报错
        """
        adj = defaultdict(dict)
        edge_details = defaultdict(list)
        
        for g in groups:
            gid = id(g)
            for mid in g.mod_ids:
                effective_rules = self.effective_rules_cache.get(mid, {})
                # 将 effective_rules 展平为 (target_id, type, source_dict, is_force)
                flat_rules = []
                # 1. 解析 Dependencies (作为极强的 load_after 处理)
                for r in effective_rules.get('dependencies', []):
                    # 如果依赖和备选都在，主包和备选包都要连线 (A 必须在 B和C 之后)
                    targets_to_link = [r['target_id']] + r.get('alternatives', [])
                    for t in targets_to_link:
                        # 依赖关系天然带有强约束性质，但仍遵循 r.get('is_force') 以防特殊指定
                        flat_rules.append((t, 'after', r['source'], r.get('is_force', True)))
                        
                # 2. 解析 Load After / Before
                for r in effective_rules.get('load_after', []):
                    flat_rules.append((r['target_id'], 'after', r['source'], r.get('is_force', False)))
                for r in effective_rules.get('load_before', []):
                    flat_rules.append((r['target_id'], 'before', r['source'], r.get('is_force', False)))
                    
                # 3. 注入到图
                for target_id, r_type, source_info, is_force in flat_rules:
                    # 如果目标根本没被激活，跳过连线
                    if target_id not in mod_to_group: continue
                    
                    target_group = mod_to_group[target_id]
                    target_gid = id(target_group)
                    if target_gid == gid: continue  # 忽略组内约束

                    # 确定方向：u -> v 表示 u 必须在 v 之前
                    # load_after: target -> self
                    # load_before: self -> target
                    if r_type == 'after': u, v = target_gid, gid
                    elif r_type == 'before': u, v = gid, target_gid
                    else: continue # incompatible 不参与拓扑排序构图

                    # 动态计算权重
                    source_type = source_info.get('type', 'unknown')
                    weight = self.get_rule_weight(source_type)
                    # 如果是 is_force，提高权重，使该边在破环时几乎不可能被切断
                    if is_force:  weight += 1000000 

                    # 记录边信息 (可能有多条规则指向同一条边)
                    edge_key = (u, v)
                    edge_details[edge_key].append({
                        "source_mod": mid,
                        "target_mod": target_id,
                        "rule_source": source_info,
                        "weight": weight,
                        "is_force": is_force
                    })

                    # 更新图中的权重（保留同方向中最强的权重）
                    current_w = adj[u].get(v, 0)
                    if weight > current_w:
                        adj[u][v] = weight
        
        return adj, edge_details

    def _break_cycles(self, adj: Dict[int, Dict[int, int]], edge_details: Dict[tuple, list], groups_map: Dict[int, AtomicGroup]) -> List[dict]:
        """
        贪婪算法消解循环：
        1. 寻找环
        2. 找到环中权重最小的边
        3. 删除该边
        4. 记录警告
        5. 重复直到无环
        """
        warnings = []
        
        # 辅助函数：深度优先搜索寻找环
        def find_cycle_path(curr, visited, stack, path_nodes):
            visited.add(curr)
            stack.add(curr)
            path_nodes.append(curr)
            
            for neighbor in list(adj[curr].keys()): # list() copy keys allowing modification
                if neighbor not in visited:
                    res = find_cycle_path(neighbor, visited, stack, path_nodes)
                    if res: return res
                elif neighbor in stack:
                    # 找到环！返回环的路径部分
                    # path_nodes 中从 neighbor 到最后的索引
                    try:
                        idx = path_nodes.index(neighbor)
                        return path_nodes[idx:]
                    except ValueError:
                        return None
            
            stack.remove(curr)
            path_nodes.pop()
            return None

        # 迭代处理，直到没有环为止
        while True:
            visited = set()
            stack = set()
            cycle_nodes = None
            
            # 遍历所有节点寻找环
            nodes = list(adj.keys())
            for node in nodes:
                if node not in visited:
                    cycle_nodes = find_cycle_path(node, visited, stack, [])
                    if cycle_nodes: break
            
            if not cycle_nodes:
                break # 图已是 DAG
            
            # 分析环，找出最弱的一环
            # 环的边是: n[0]->n[1], n[1]->n[2], ..., n[k]->n[0]
            cycle_edges = []
            for i in range(len(cycle_nodes)):
                u = cycle_nodes[i]
                v = cycle_nodes[(i + 1) % len(cycle_nodes)]
                weight = adj[u][v]
                cycle_edges.append((u, v, weight))
            
            # 找到权重最小的边
            # 如果权重相同，可以按稳定性排序（这里简单按遍历顺序）
            min_edge = min(cycle_edges, key=lambda x: x[2])
            u_min, v_min, min_w = min_edge
            
            # 构造警告信息
            broken_rules = edge_details.get((u_min, v_min), [])
            # 取出权重匹配的规则作为“罪魁祸首”
            culprit_rules = [r for r in broken_rules if r['weight'] == min_w]
            
            u_group_name = groups_map[u_min].mod_ids[0]
            v_group_name = groups_map[v_min].mod_ids[0]

            for rule in culprit_rules:
                warnings.append({
                    "type": "cycle_broken",
                    "level": "warn",
                    "message": f"为解决循环依赖，已忽略 {rule['rule_source']['name']}：[{rule['source_mod']}] 要求在 [{rule['target_mod']}] 之后/之前 的限制。",
                    "rule_type": rule['rule_source'],
                    "source_id": rule['source_mod'],
                    "target_id": rule['target_mod'],
                    "detail": rule,
                })
            
            # 物理删除边
            del adj[u_min][v_min]
            logger.warning(f"Cycle broken: removed edge {u_group_name} -> {v_group_name} (weight {min_w})")

        return warnings

    def sort(self, active_ids: List[str]):
        """
        最终排序：原子组 -> 权重修正 -> 依赖构图 -> 权重传播 -> 拓扑排序 (带名称稳定性)
        """
        logger.info(f"Starting sort for {len(active_ids)} mods...")
        all_mods_data = ModDAO.get_profile_mods(self.context)
        mod_map = {m['package_id'].lower(): m for m in all_mods_data}
        current_assets_ids = list(mod_map.keys())
        from backend.database.dao import GroupDAO
        all_groups = GroupDAO.get_groups_structured_by_mod_ids(current_assets_ids)
        # 建立反向映射: package_id -> [group_name1, group_name2]
        mod_groups_map = defaultdict(list)
        for g in all_groups:
            for mid in g['mod_ids']:
                mod_groups_map[mid.lower()].append(g['name'])
        # 将分组名注入到 mod_map 中
        for mid, m_data in mod_map.items():
            m_data['groups'] = mod_groups_map.get(mid, [])
        
        # --- 0. 依赖项自动修补 (受开关控制) ---
        active_set = set(id.lower() for id in active_ids)
        auto_activated_deps = []
        
        self.effective_rules_cache = {} # 全局规则缓存字典
        for mid, m_data in mod_map.items():
            self.effective_rules_cache[mid] = self.rule_mgr.get_effective_mod_rules(mid, m_data)
        
        MAX_ITERATIONS = 15  # [新增] 设定最大迭代深度阈值
        
        # 默认 False 保持保守行为
        if settings.config.auto_activate_dependencies or False:
            changed = True
            iteration_count = 0  # 迭代计数器
            # 因为被自动激活的依赖可能还有它自己的依赖，所以需要循环挖掘直到没有新增
            while changed and iteration_count < MAX_ITERATIONS:
                changed = False
                iteration_count += 1
                for mid in list(active_set):
                    m_data = mod_map.get(mid, {})
                    rules = self.effective_rules_cache.get(mid, {})
                    
                    for dep in rules.get('dependencies', []):
                        target = dep['target_id']
                        alts = dep.get('alternatives', [])
                        
                        # 如果主目标或任一备选目标已在激活列表中，则视为满足，跳过
                        if target in active_set or any(alt in active_set for alt in alts):
                            continue
                            
                        # 缺失依赖，尝试优先激活主目标
                        if target in mod_map:
                            active_set.add(target)
                            auto_activated_deps.append(target)
                            changed = True
                        else:
                            # 主目标本地没有，尝试激活存在于本地的备选包
                            for alt in alts:
                                if alt in mod_map:
                                    active_set.add(alt)
                                    auto_activated_deps.append(alt)
                                    changed = True
                                    break
            # 触发阈值警告
            if iteration_count >= MAX_ITERATIONS:
                logger.warning(f"依赖自动补全达到最大迭代次数({MAX_ITERATIONS}次)，可能存在循环依赖配置，已强制终止延伸。")
        
        expanded_active_ids = list(active_set)
        # 1. 将扩展后的激活列表转化为原子组
        groups = self.build_atomic_groups(expanded_active_ids)
        mod_to_group = {mid: g for g in groups for mid in g.mod_ids}
        group_ids = [id(g) for g in groups]
        groups_by_id = {id(g): g for g in groups}

        # 2. 计算节点自身权重 (Weight Propagation base)
        group_base_weights = {}
        group_sort_keys = {}  # 存储 (Name, PackageID) 用于稳定排序
        for g in groups:
            weights = []
            # 获取组内第一个 Mod 的信息作为该组的“代表名称”
            first_mod_id = g.mod_ids[0]
            first_mod_data = mod_map.get(first_mod_id, {})
            
            # A. 确定排序名称 (Name)
            # 优先用别名 -> 名字 -> ID
            if settings.config.sort_mods_by == "alias_name":
                display_name = first_mod_data.get('alias_name') or first_mod_data.get('name') or first_mod_id
            elif settings.config.sort_mods_by == "name":
                display_name = first_mod_data.get('name') or first_mod_id
            else:
                display_name = first_mod_id
            
            # 移除非字母字符并转小写，确保排序自然 (比如忽略 [1.4] 这种前缀)
            # 这里简单做 lower() strip() 即可，如果想更高级可以去掉 []
            sort_name = display_name.lower().strip()
            
            # B. 确定唯一ID (PackageID) - 用于绝对稳定性
            sort_id = first_mod_id.lower()

            # 存储次要排序键
            group_sort_keys[id(g)] = (sort_name, sort_id)

            # C. 计算权重
            for mid in g.mod_ids:
                
                # 获取该 Mod 生效的所有规则
                effective_rules = self.effective_rules_cache.get(mid, {})
                weight_info = effective_rules.get("weight_info", {})
                # 获取该 Mod 已经由 RuleManager 算好的最终规则集
                effective_rules = self.effective_rules_cache.get(mid, {})
                weight_info = effective_rules.get("weight_info", {})
                # [新增] 纯粹的算术应用，完全不关心业务逻辑
                w = weight_info.get("base_weight", 500) + weight_info.get("weight_shift", 0)
                # [新增] 处理决定性的绝对位置
                abs_type = weight_info.get("absolute_type")
                if abs_type == "top":
                    w = 0
                elif abs_type == "bottom":
                    w = 10000 
                weights.append(w)
                
                """
                has_absolute_override = False
                # 应用绝对位置覆盖 (Top / Bottom)
                override = effective_rules.get("weight_override")
                if override:
                    if override["type"] == "top": w = 0
                    elif override["type"] == "bottom": w = 10000 # 建议设大一点，1000不够大
                    has_absolute_override = override['source']['type'] # 记录来源
                
                # 只有在没有强制绝对覆盖，或者动态规则优先级比绝对覆盖更高时，才应用动态权重
                dyn_priority = self.rule_mgr.get_source_priority("dynamic")
                override_priority = self.rule_mgr.get_source_priority(has_absolute_override) if has_absolute_override else 999

                if dyn_priority <= override_priority or not has_absolute_override:
                    if self.rule_mgr.settings.get("dynamic_rules_enabled", True):
                        matched_dyn = self.rule_mgr.get_matching_dynamic_rules(m_data)
                        for rule in matched_dyn:
                            act = rule.get("action", {})
                            if act.get('type') == 'weight_shift': w += act.get('value', 0)
                            elif act.get('type') == 'weight_set': w = act.get('value', w)
                            # 动态规则自带的 top/bottom 操作
                            elif act.get('type') == 'top': w = 0
                            elif act.get('type') == 'bottom': w = 10000
                weights.append(w)
                """
                
            # 一个原子组如果有多个 Mod 联锁，取最小的权重作为整个组的启动权重
            group_base_weights[id(g)] = min(weights) if weights else 500
        # 3. 构建加权依赖图
        adj, edge_details = self._build_weighted_graph(groups, mod_map, mod_to_group)
        
        # 4. 核心步骤：消解循环
        cycle_warnings = self._break_cycles(adj, edge_details, groups_by_id)

        # 5. 计算入度
        in_degree = defaultdict(int)
        for u in adj:
            for v in adj[u]:
                in_degree[v] += 1
        # 确保所有节点都有入度记录
        for gid in group_ids:
            if gid not in in_degree:
                in_degree[gid] = 0

        # 6. 权重传播 (Inherited Weight Propagation)
        # 注意：这里的权重是为了让“基础权重小(应当排在前面)”的节点，能够拉低其依赖项的权重
        # 如果 A(500) -> B(900)，则 B 不应该跑到 A 前面去，保持拓扑序即可。
        # 如果 A(900) -> B(500)，根据拓扑序 A 必须在 B 前面，此时 A 的权重应被拉低到 500 甚至更低，以便在堆中优先弹出
        effective_weights = group_base_weights.copy()
        # 简单的传播算法：如果 u -> v，u 应该比 v 早。
        # 在 Kahn 算法的 PriorityQueue 中，希望早出来的权重小。
        # adj[u] = {v: w} 表示 u -> v，即 u 在前。
        # 如果 effective_weights[v] (后) < effective_weights[u] (前)
        # 通常是 Core(0) -> Mod(500)。
        changed = True
        while changed:
            changed = False
            for u in list(adj.keys()):
                for v in adj[u]:
                    if effective_weights[v] < effective_weights[u]:
                        effective_weights[u] = effective_weights[v]
                        changed = True

        # 7. Kahn算法拓扑排序 (带优先级堆)
        queue = []
        for gid in group_ids:
            if in_degree[gid] == 0:
                # 推入堆的元组结构：
                # (有效权重, 排序名称, 唯一ID, 内存地址)
                # Python 对元组比较是按顺序逐个比较的
                s_name, s_id = group_sort_keys[gid]
                heapq.heappush(queue, (effective_weights[gid], s_name, s_id, gid))

        sorted_groups = []
        while queue:
            # 弹出时解包
            w, s_name, s_id, gid = heapq.heappop(queue)
            if gid not in groups_by_id: continue # 安全检查
            g = groups_by_id[gid]
            sorted_groups.append(g)
            if gid in adj:
                for neighbor in adj[gid]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        n_s_name, n_s_id = group_sort_keys[neighbor]
                        n_w = effective_weights[neighbor]
                        heapq.heappush(queue, (n_w, n_s_name, n_s_id, neighbor))

        # 8. 兜底检查（虽然已break_cycles，但为了绝对稳健）
        if len(sorted_groups) < len(groups):
            # 理论上不会进这里，除非 break_cycles 逻辑有漏网之鱼
            sorted_group_ids = {id(g) for g in sorted_groups}
            remaining_groups = [g for g in groups if id(g) not in sorted_group_ids]
            # 简单追加
            sorted_groups.extend(remaining_groups)
            cycle_warnings.append({
                "type": "cycle_fatal",
                "level": "error",
                "message": "排序算法在循环消解后仍有残留节点，已强制追加到末尾。",
                "affected_ids": [mid for rg in remaining_groups for mid in rg.mod_ids]
            })

        # 9. 输出结果
        final_list = []
        interlock_auto_activated  = []
        for g in sorted_groups:
            final_list.extend(g.mod_ids)
            interlock_auto_activated .extend(g.auto_activated)
        
        # 10. 合并自动激活的依赖项，形成最终的自动激活列表
        all_auto_activated = list(set(interlock_auto_activated + auto_activated_deps))

        return {
            "sorted_ids": final_list,
            "auto_activated": all_auto_activated,
            "warnings": cycle_warnings # 包含冲突消解的日志
        }
    
    
    
    
