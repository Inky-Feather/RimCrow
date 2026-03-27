from typing import List, Dict, Optional, Set, Tuple, Any
import heapq
from collections import deque, defaultdict
from backend.database.dao import ModDAO
from backend.database.models import ModInterlock
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
    
    def ensure_mods(self, active_ids: List[str], mod_map: Dict[str, dict]) -> Tuple[List[str], List[str]]:
        """
        防呆机制：强制保证官方核心组件在激活列表中，且参与排序。
        如果物理存在，则强制加入 active_ids。
        """
        core_sequence = [
            "ludeon.rimworld", 
            # "ludeon.rimworld.royalty", 
            # "ludeon.rimworld.ideology", 
            # "ludeon.rimworld.biotech", 
            # "ludeon.rimworld.anomaly"
        ]
        tool_mods = [
            "rmm.companion"
        ]
        active_set = set(active_ids)
        need_added_ids = []
        
        for core_id in core_sequence:
            if core_id in mod_map and core_id not in active_set:
                active_ids.append(core_id)
                active_set.add(core_id)
                need_added_ids.append(core_id)
        
        if settings.config.enable_tool_mods:
            for tool_id in tool_mods:
                if tool_id in mod_map and tool_id not in active_set:
                    active_ids.append(tool_id)
                    active_set.add(tool_id)
                    need_added_ids.append(tool_id)
        
        if need_added_ids:
            logger.info(f"防呆拦截: 强制补全缺失的核心组件 -> {need_added_ids}")
            
        return active_ids, need_added_ids

    def build_atomic_groups(self, active_ids: List[str], mod_map: Dict[str, dict]) -> Tuple[List[AtomicGroup], List[dict]]:
        """
        第一步：将激活列表转化为原子组列表
        """
        # 1. 获取所有 Mod 的联锁数据
        # 注意：为了性能，一次性查出所有涉及到的 Mod 数据
        # 即使有的 Mod 不在 active_ids 里，只要它被联锁引用了，也要查
        active_set = set(id.lower() for id in active_ids)
        visited_in_chain = set()
        atomic_groups = []
        warnings = []
        
        # 1. 提取所有激活 Mod 涉及的联锁组 ID
        involved_interlock_ids = set()
        for mid in active_set:
            mod_info = mod_map.get(mid)
            if mod_info and mod_info.get('interlock_id'):
                involved_interlock_ids.add(mod_info['interlock_id'])
                
        # 2. 从数据库批量拉取这些联锁序列
        interlocks = {}
        if involved_interlock_ids:
            locks = ModInterlock.select().where(ModInterlock.id << list(involved_interlock_ids)) # type: ignore
            interlocks = {lock.id: lock.chain for lock in locks}

        # 3. 处理联锁组
        for lock_id, chain in interlocks.items():
            effective_chain = []
            missing_in_local = []
            missing_in_active = []
            
            for pid in chain:
                pid = pid.lower()
                visited_in_chain.add(pid)
                
                # 检查物理存在性
                if pid not in mod_map:
                    missing_in_local.append(pid)
                    continue
                    
                # 检查激活状态 (联锁中的成员，即使未激活，如果是跟随激活的策略，强制补齐)
                if pid not in active_set:
                    missing_in_active.append(pid)
                    
                effective_chain.append(pid)
            
            # 生成警告：联锁由于缺失发生了降级
            if missing_in_local:
                warnings.append({
                    "type": "interlock_broken_local",
                    "level": "warn",
                    "interlock_id": lock_id,
                    "message": f"联锁组由于部分模组在本地缺失而降级。缺失项: {missing_in_local}"
                })
            
            # 如果存活的链条 >= 1，包装成 AtomicGroup
            if effective_chain:
                group = AtomicGroup(effective_chain)
                group.auto_activated = missing_in_active
                atomic_groups.append(group)

        # 4. 处理独立的单体 Mod (未参与联锁的)
        for mid in active_set:
            if mid not in visited_in_chain:
                # 幽灵 Mod (本地无数据) 或普通单体 Mod
                atomic_groups.append(AtomicGroup([mid]))

        return atomic_groups, warnings


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
        # 防呆：注入官方核心模组
        active_ids, need_added_ids = self.ensure_mods(active_ids, mod_map)
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
        
        MAX_ITERATIONS = 15  # 设定最大迭代深度阈值
        
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
        groups, interlock_warnings = self.build_atomic_groups(expanded_active_ids, mod_map)
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
            is_top = False
            is_bottom = False
            for mid in g.mod_ids:
                # 获取该 Mod 生效的所有规则
                effective_rules = self.effective_rules_cache.get(mid, {})
                weight_info = effective_rules.get("weight_info", {})
                # 纯粹的算术应用，完全不关心业务逻辑
                w = weight_info.get("base_weight", 500) + weight_info.get("weight_shift", 0)
                # 处理决定性的绝对位置
                abs_type = weight_info.get("absolute_type")
                if abs_type == "top": w = 0; is_top = True  # 标记组内有置顶成员
                elif abs_type == "bottom": w = 10000; is_bottom = True  # 标记组内有置底成员
                weights.append(w)
                
            # # 一个原子组如果有多个 Mod 联锁，取最小的权重作为整个组的启动权重
            # group_base_weights[id(g)] = min(weights) if weights else 500
            # 修正：更精细地计算原子组的最终基础权重
            if not weights:
                group_base_weights[id(g)] = 500
            elif is_top:
                # 只要有一个成员要置顶，整个组就必须置顶
                group_base_weights[id(g)] = 0
            elif is_bottom:
                # 在没有置顶成员的前提下，只要有一个成员要置底，整个组就置底
                group_base_weights[id(g)] = 10000
            else:
                # 如果组内都是普通模组，取最小权重，满足最靠前的约束
                group_base_weights[id(g)] = min(weights)
            
        # 3. 构建加权依赖图
        adj, edge_details = self._build_weighted_graph(groups, mod_map, mod_to_group)
        # 4. 核心步骤：消解循环
        cycle_warnings = self._break_cycles(adj, edge_details, groups_by_id)
        # 将联锁断裂的警告合并进去
        cycle_warnings.extend(interlock_warnings)

        # 5. 计算入度和出度
        in_degree = defaultdict(int)
        for u in adj:
            for v in adj[u]:
                in_degree[v] += 1
        for gid in group_ids:
            if gid not in in_degree:
                in_degree[gid] = 0

        # [新增] 5.5 预计算所有节点的“依赖尾巴大小”
        # 这是一个全局的、结构性的指标
        tail_size_cache = {}
        def get_tail_size(start_node_id):
            if start_node_id in tail_size_cache:
                return tail_size_cache[start_node_id]
            q = deque([start_node_id])
            visited = {start_node_id}
            count = 0
            while q:
                curr_id = q.popleft()
                count += 1
                for neighbor_id in adj.get(curr_id, []):
                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        q.append(neighbor_id)
            tail_size_cache[start_node_id] = count
            return count
        # 为所有节点计算尾巴大小
        all_tail_sizes = {gid: get_tail_size(gid) for gid in group_ids}
        
        # 6. 双向权重传播 (Bidirectional Weight Propagation)
        # 注意：这里的权重是为了让“基础权重小(应当排在前面)”的节点，能够拉低其依赖项的权重
        # 如果 A(500) -> B(900)，则 B 不应该跑到 A 前面去，保持拓扑序即可。
        # 如果 A(900) -> B(500)，根据拓扑序 A 必须在 B 前面，此时 A 的权重应被拉低到 500 甚至更低，以便在堆中优先弹出
        effective_weights = group_base_weights.copy()
        # 简单的传播算法：如果 u -> v，u 应该比 v 早。
        # 在 Kahn 算法的 PriorityQueue 中，希望早出来的权重小。
        # adj[u] = {v: w} 表示 u -> v，即 u 在前。
        # 如果 effective_weights[v] (后) < effective_weights[u] (前)
        # 通常是 Core(0) -> Mod(500)。
        
        # changed = True
        # while changed:
        #     changed = False
        #     for u in list(adj.keys()):
        #         for v in adj[u]:
        #             # u -> v 意味着拓扑序中 u 必须在 v 之前加载
        #             # 传染 A：Top 拉升 (向上看齐)
        #             # 只有当后置 v 非常急切想要先出场 (< 500)，前置 u 才必须被拉上来
        #             if effective_weights[v] <= 500 and effective_weights[u] > effective_weights[v]:
        #                 effective_weights[u] = effective_weights[v]
        #                 changed = True
        #             # 传染 B：Bottom 下压 (向下看齐)
        #             # 只有当前置 u 非常想赖到最后 (>= 500, 如置底是 10000)，后置 v 必须被压制到更后方
        #             if effective_weights[u] > 500 and effective_weights[v] < effective_weights[u]:
        #                 effective_weights[v] = effective_weights[u]
        #                 changed = True
            
        # 对于非循环图，迭代次数等于节点数即可保证完全传播
        for _ in range(len(groups) + 1):
            changed = False
            # 遍历所有边 (u -> v)
            for u, neighbors in adj.items():
                for v in neighbors:
                    # 规则1: 前者(u)的“推后”意愿会影响后者(v)
                    if effective_weights[v] < effective_weights[u]:
                        effective_weights[v] = effective_weights[u]
                        changed = True
                    
                    # 规则2: 后者(v)的“提前”意愿会影响前者(u)
                    if effective_weights[u] > effective_weights[v]:
                        effective_weights[u] = effective_weights[v]
                        changed = True
            if not changed:
                break

        # 7. Kahn算法拓扑排序 (带优先级堆和新的极值对比局规则)
        queue = []
        for gid in group_ids:
            if in_degree[gid] == 0:
                # 推入堆的元组结构：
                # (有效权重, 排序名称, 唯一ID, 内存地址)
                # Python 对元组比较是按顺序逐个比较的
                s_name, s_id = group_sort_keys[gid]
                w = effective_weights[gid]         # 最终权重
                base_w = group_base_weights[gid]   # 原始权重
                # 3. 依赖尾巴大小极值对比指标 (越大越靠前)
                tail_size = all_tail_sizes.get(gid, 1)
                tail_breaker = -tail_size 
                # 元组结构：(最终权重, 原始权重, 尾巴极值对比指标, 名称, ID, GID)
                # 注意：只有在权重为0或10000时，这个对比指标才真正有意义。为了代码简洁，我们对所有节点都计算它。
                heapq.heappush(queue, (w, base_w, tail_breaker, s_name, s_id, gid))

        sorted_groups = []
        while queue:
            # 弹出时解包
            w, base_w, tail_breaker, s_name, s_id, gid = heapq.heappop(queue)
            if gid not in groups_by_id: continue # 安全检查
            g = groups_by_id[gid]
            sorted_groups.append(g)
            if gid in adj:
                for neighbor in adj[gid]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        n_s_name, n_s_id = group_sort_keys[neighbor]
                        n_w = effective_weights[neighbor]
                        n_base_w = group_base_weights[neighbor]
                        n_tail_size = all_tail_sizes.get(neighbor, 1)
                        n_tail_breaker = -n_tail_size
                        heapq.heappush(queue, (n_w, n_base_w, n_tail_breaker, n_s_name, n_s_id, neighbor))

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
    

    def smart_insert_mods(self, target_ids: List[str], current_list: List[str], mod_map: Dict[str, dict]) -> List[str]:
        """
        批量无损插入算法：
        在不打乱 current_list 现有顺序的前提下，为一批 target_ids 寻找最合适的插入点。
        """
        if not target_ids: return current_list
        new_list = current_list.copy()
        existing_in_list = set(new_list) # 假设 current_list 中的 ID 也已是小写
        # 1. 自动扩展：提取所有 target_ids 包含的有效本地依赖项
        expanded_targets = set(target_ids)
        # [IMPROVEMENT] 使用 deque 替代 list 作为高效队列
        # 初始化队列时，就排除掉已经存在于列表中的模组
        queue = deque(expanded_targets - existing_in_list)
        # 扩展待插入列表，把所有需要插入的模组（包括它们的依赖）都加入 expanded_targets
        # 这个过程会处理循环依赖，因为 expanded_targets 是一个 set
        processed_for_deps = set(existing_in_list) # 记录已经处理过依赖扩展的，防止重复计算
        processed_for_deps.update(queue)
        while queue:
            curr = queue.popleft() # [IMPROVEMENT] O(1) 操作
            target_data = mod_map.get(curr)
            if not target_data: continue
            rules = self.effective_rules_cache.get(curr)
            if not rules:
                rules = self.rule_mgr.get_effective_mod_rules(curr, target_data)
                self.effective_rules_cache[curr] = rules
            for dep in rules.get('dependencies', []):
                dep_id = dep['target_id'] # 假设规则中的 ID 也是小写
                # 如果依赖项本地存在，并且我们还没有处理过它
                if dep_id in mod_map and dep_id not in processed_for_deps:
                    expanded_targets.add(dep_id)
                    queue.append(dep_id)
                    processed_for_deps.add(dep_id)
        # 2. 收集真正需要插入的模组的数据
        # [FIX] 核心修复：只处理不在 original list 中的模组
        ids_to_process = expanded_targets - existing_in_list
        to_insert = []
        for tid in ids_to_process:
            target_data = mod_map.get(tid)
            if not target_data: continue
            rules = self.effective_rules_cache.get(tid)
            if not rules:
                rules = self.rule_mgr.get_effective_mod_rules(tid, target_data)
                self.effective_rules_cache[tid] = rules
            weight = rules.get("weight_info", {}).get("final_weight", 500)
            to_insert.append({"id": tid, "weight": weight, "rules": rules})
            # [FIX] 移除无效的 existing_in_list.add(tid)
        if not to_insert: return new_list
        # 3. 预排序
        to_insert.sort(key=lambda x: x["weight"])
        for item in to_insert:
            tid_l = item["id"]
            rules = item["rules"]
            weight = item["weight"]
            current_lower = [m.lower() for m in new_list]
            min_idx = 0                  # 必须插在这个索引之后
            max_idx = len(current_lower) # 必须插在这个索引之前
            # A & B: 正向约束 (新模组对老模组的要求)
            after_targets = [r['target_id'] for r in rules.get('load_after', [])] + \
                            [r['target_id'] for r in rules.get('dependencies', [])]
            for t in after_targets:
                if t in current_lower:
                    min_idx = max(min_idx, current_lower.index(t) + 1)
                    
            before_targets = [r['target_id'] for r in rules.get('load_before', [])]
            for t in before_targets:
                if t in current_lower: max_idx = min(max_idx, current_lower.index(t))
            # [核心修复 1] C & D: 反向约束 (老模组对新模组的要求)
            # 遍历当前列表，检查老模组是否依赖/前置于将要插入的模组
            for i, comp_id in enumerate(current_lower):
                comp_rules = self.effective_rules_cache.get(comp_id)
                if not comp_rules:
                    # 如果缓存没有，尝试获取 (理论上应该都有，这是兜底)
                    comp_data = mod_map.get(comp_id, {})
                    comp_rules = self.rule_mgr.get_effective_mod_rules(comp_id, comp_data)
                    self.effective_rules_cache[comp_id] = comp_rules
                # C. 老模组必须在“我”之后 (老模组依赖/LoadAfter我) -> “我”必须在老模组之前
                comp_afters = [r['target_id'] for r in comp_rules.get('load_after', [])] + \
                            [r['target_id'] for r in comp_rules.get('dependencies', [])]
                if tid_l in comp_afters: max_idx = min(max_idx, i)
                # D. 老模组必须在“我”之前 (老模组LoadBefore我) -> “我”必须在老模组之后
                comp_befores = [r['target_id'] for r in comp_rules.get('load_before', [])]
                if tid_l in comp_befores: min_idx = max(min_idx, i + 1)
            # ==========================================
            # E. 结合权重的精准落位 (附带平级决胜机制)
            # ==========================================
            insert_pos = min_idx
            if min_idx > max_idx:
                logger.warning(f"智能插入 {tid_l} 规则矛盾 (min:{min_idx} > max:{max_idx})，强制使用前置。")
                insert_pos = min_idx
            else:
                inserted = False
                if weight <= 0:
                    insert_pos = min_idx # 绝对置顶
                    inserted = True
                elif weight >= 10000:
                    insert_pos = max_idx # 绝对置底
                    inserted = True
                else:
                    # 核心突破：在合法区间内，顺着找第一个比自己重，或平级但字母顺序靠后的 Mod
                    for i in range(min_idx, max_idx):
                        comp_id = current_lower[i]
                        comp_rules = self.effective_rules_cache.get(comp_id, {})
                        comp_w = comp_rules.get("weight_info", {}).get("final_weight", 500)
                        
                        if comp_w > weight:
                            # 找到了比我重的（例如 500 遇到了 850材质包），插在它前面
                            insert_pos = i
                            inserted = True
                            break
                        elif comp_w == weight:
                            # [核心修复 2] 权重相同（都是500），引入字母顺序作为决胜局 (Tie-breaker)
                            # 这样新模组就能自然地按照字母顺序融入旧模组列表中，而不会一味沉底
                            if comp_id > tid_l:
                                insert_pos = i
                                inserted = True
                                break
                                
                if not inserted:
                    insert_pos = max_idx # 区间内没东西，或者我是最轻的，插在区间末尾
            new_list.insert(insert_pos, tid_l)
            logger.info(f"智能插入: {tid_l} (Weight:{weight}) -> Index {insert_pos}")
            
        return new_list
        
    
