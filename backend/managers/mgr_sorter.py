from typing import List, Dict, Optional, Set, Tuple, Any
import heapq
from collections import deque, defaultdict
from backend.database.dao import ModDAO
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
    RULE_PRIORITIES = {
        'native': 10000,
        'community': 1000,
        'user': 100,
        'user_dynamic': 10,
        'unknown': 1
    }
    def __init__(self):
        self.dao = ModDAO()
        self.rule_mgr = RuleManager()
        self.SPECIAL_WEIGHTS = {
            'brrainz.harmony': 0,
            'ludeon.rimworld': 50,
            'ludeon.rimworld.royalty': 51,
            'ludeon.rimworld.ideology': 52,
            'ludeon.rimworld.biotech': 53,
            'ludeon.rimworld.anomaly': 54,
            'unlimitedhugs.hugslib': 110,
        }

    def build_atomic_groups(self, active_ids: List[str]) -> List[AtomicGroup]:
        """
        第一步：将激活列表转化为原子组列表
        """
        # 1. 获取所有 Mod 的联锁数据
        # 注意：为了性能，我们一次性查出所有涉及到的 Mod 数据
        # 即使有的 Mod 不在 active_ids 里，只要它被联锁引用了，也要查
        all_mods_data = ModDAO.get_all_mods_with_user_data()
        mod_map = {m['package_id'].lower(): m for m in all_mods_data}
        active_set = set(id.lower() for id in active_ids)
        visited = set()
        atomic_groups = []

        # 辅助函数：深度优先搜索构建链条
        def trace_chain(current_id: str, current_chain: List[str], auto_activated: List[str]):
            if current_id in visited:
                return
            visited.add(current_id)
            # 如果当前 ID 不在激活列表中，记录为自动激活
            if current_id not in active_set:
                auto_activated.append(current_id)
            current_chain.append(current_id)
            mod_info = mod_map.get(current_id)
            if not mod_info:
                return
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

    def calculate_mod_base_weight(self, mod_data: dict) -> int:
        """
        根据 Mod 数据计算单一 Mod 的基础权重
        """
        pkg_id = mod_data.get('package_id', '').lower().strip()
        # 1. 检查特殊硬编码 ID
        if pkg_id in self.SPECIAL_WEIGHTS:
            return self.SPECIAL_WEIGHTS[pkg_id]
        # 2. 根据作者判定 (官方作者)
        authors = mod_data.get('author', [])
        if 'Ludeon Studios' in authors:
            return 60
        # 3. 根据 Mod 类型判定 (来自 analyzer.py 的分析结果)
        mod_type = str(mod_data.get('user_mod_type') or mod_data.get('mod_type', 'Unknown')).strip()
        # if pkg_id == 'optimizer.zh':
        #     print(f"optimizer.zh 权重: {mod_type},{mod_data.get('mod_type', 'Unknown')}, mod_data: {mod_data}")
        if mod_type == 'LanguagePack':
            return 900  # 汉化包置底
        if mod_type == 'Texture':
            return 850  # 纹理包置后
        if mod_type == 'Audio':
            return 860  # 音频包置后
        # 4. 根据 ID 关键字模糊判定
        if '.lib' in pkg_id or 'library' in pkg_id:
            return 150
        if 'framework' in pkg_id:
            return 160
        # 5. 默认权重 (普通 Mod)
        return 500

    def _get_all_constraints(self, mid: str, mod_full_data: dict) -> List[Tuple[str, str, dict]]:
        """
        现在的逻辑：直接问 RuleManager 拿已经过滤好的生效规则
        """
        # 1. 拿原始聚合数据
        raw_constraints = self.rule_mgr.collect_constraints(mid, mod_full_data)
        
        # 2. 格式化为排序器兼容的元组 (target, type, info)
        # 过滤掉 dynamic 类型（因为 dynamic 是在计算权重环节处理的，不属于构图约束）
        formatted = []
        for c in raw_constraints:
            if c['type'] != 'dynamic':
                formatted.append((c['target'], c['type'], c['source']))
        
        return formatted

    def _get_all_constraints0(self, mid: str, mod_full_data: dict) -> List[Tuple[str, str, dict]]:
        """
        核心函数：获取一个 Mod 涉及的所有先后约束
        返回: [(target_id, type, source_info), ...]
        type: 'after' | 'before' | 'incompatible'
        """
        mid = mid.lower()
        constraints = []
        # 1. Native (About.xml)
        for p in mod_full_data.get('dependencies_mods', []):
            constraints.append((p['package_id'].lower(), 'after', {"name": "原生依赖", "type": "native"}))
        for p in mod_full_data.get('load_after_mods', []):
            constraints.append((p.lower(), 'after', {"name": "原生前置", "type": "native"}))
        for p in mod_full_data.get('load_before_mods', []):
            constraints.append((p.lower(), 'before', {"name": "原生后置", "type": "native"}))
        for p in mod_full_data.get('incompatible_mods', []):
            constraints.append((p.lower(), 'incompatible', {"name": "原生冲突", "type": "native"}))

        # 2. Community Rules (JSON)
        comm = self.rule_mgr.community_rules.get(mid, {})
        for target, info in comm.get("loadAfter", {}).items():
            constraints.append((target.lower(), 'after', {"name": "社区前置", "type": "community", "info": info}))
        for target, info in comm.get("loadBefore", {}).items():
            constraints.append((target.lower(), 'before', {"name": "社区后置", "type": "community", "info": info}))
        for target, info in comm.get("incompatibleWith", {}).items():
            constraints.append((target.lower(), 'incompatible', {"name": "社区冲突", "type": "community", "info": info}))

        # 3. User Single Rules
        user_s = self.rule_mgr.user_mod_rules.get(mid, {})
        for target, info in user_s.get("loadAfter", {}).items():
            constraints.append((target.lower(), 'after', {"name": "用户前置", "type": "user", "info": info}))
        for target, info in user_s.get("loadBefore", {}).items():
            constraints.append((target.lower(), 'before', {"name": "用户后置", "type": "user", "info": info}))
        for target, info in user_s.get("incompatibleWith", {}).items():
            constraints.append((target.lower(), 'incompatible', {"name": "用户冲突", "type": "user", "info": info}))

        # 4. User Dynamic Rules (仅处理明确的 LoadAfter/Before 动作)
        matched_dyn = self.rule_mgr.get_matching_dynamic_rules(mod_full_data)
        for rule in matched_dyn:
            act = rule.get("action", {})
            if act['type'] == 'load_after':
                constraints.append((act['value'].lower(), 'after', {"name": rule['name'], "type": "user_dynamic"}))
            elif act['type'] == 'load_before':
                constraints.append((act['value'].lower(), 'before', {"name": rule['name'], "type": "user_dynamic"}))

        return constraints


    def check_health(self, active_ids: List[str]) -> List[dict]:
        """
        【常态化提示核心】不排序，仅检查当前顺序是否违背任何规则
        """
        all_mods_data = ModDAO.get_all_mods_with_user_data()
        mod_map = {m['package_id'].lower(): m for m in all_mods_data}
        id_to_idx = {mid.lower(): i for i, mid in enumerate(active_ids)}
        active_set = set(id_to_idx.keys())
        
        issues = []
        for mid in active_ids:
            mid_l = mid.lower()
            m_data = mod_map.get(mid_l, {})
            rules = self._get_all_constraints(mid_l, m_data)
            
            for target_id, r_type, source in rules:
                if target_id not in active_set: continue
                t_idx = id_to_idx[target_id]
                m_idx = id_to_idx[mid_l]
                if r_type == 'after' and t_idx > m_idx:
                    issues.append({
                        "mod_id": mid, "type": "wrong_order", "level": "warn",
                        "message": f"排序错误：应位于 [[{target_id}]] 之后 ({source['name']})",
                        "target_id": target_id, "source": source
                    })
                elif r_type == 'before' and t_idx < m_idx:
                    issues.append({
                        "mod_id": mid, "type": "wrong_order", "level": "warn",
                        "message": f"排序错误：应位于 [[{target_id}]] 之前 ({source['name']})",
                        "target_id": target_id, "source": source
                    })
                elif r_type == 'incompatible':
                    issues.append({
                        "mod_id": mid, "type": "incompatible", "level": "error",
                        "message": f"模组冲突：与 [[{target_id}]] 不兼容 ({source['name']})",
                        "target_id": target_id, "source": source
                    })
        return issues

    # =========================================================================
    # 加权图构建与循环消解
    # =========================================================================

    def _build_weighted_graph(self, groups: List[AtomicGroup], mod_map: Dict[str, dict], mod_to_group: Dict[str, AtomicGroup]):
        """
        构建带权重的依赖图
        返回: 
          adj: Dict[int, Dict[int, int]]  adj[u][v] = weight (表示 u 必须在 v 之前，权重 weight)
          edge_info: Dict[tuple, list] 记录每条边是由哪些具体规则生成的，用于报错
        """
        adj = defaultdict(dict)
        edge_details = defaultdict(list)
        
        for g in groups:
            gid = id(g)
            for mid in g.mod_ids:
                constraints = self._get_all_constraints(mid, mod_map.get(mid, {}))
                for target_id, r_type, source in constraints:
                    if target_id not in mod_to_group: continue
                    target_group = mod_to_group[target_id]
                    target_gid = id(target_group)
                    
                    if target_gid == gid: continue # 忽略组内约束

                    # 确定方向：u -> v 表示 u 必须在 v 之前
                    # load_after: target -> self
                    # load_before: self -> target
                    if r_type == 'after':
                        u, v = target_gid, gid
                    elif r_type == 'before':
                        u, v = gid, target_gid
                    else:
                        continue # incompatible 不参与拓扑排序构图

                    # 计算权重
                    rule_type = source.get('type', 'unknown')
                    weight = self.RULE_PRIORITIES.get(rule_type, 1)

                    # 记录边信息 (可能有多条规则指向同一条边)
                    edge_key = (u, v)
                    edge_details[edge_key].append({
                        "source_mod": mid,
                        "target_mod": target_id,
                        "rule_source": source,
                        "weight": weight
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
        # 1. 初始化
        groups = self.build_atomic_groups(active_ids)
        all_mods_data = ModDAO.get_all_mods_with_user_data()
        mod_map = {m['package_id'].lower(): m for m in all_mods_data}
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
                m_data = mod_map.get(mid, {})
                w = self.calculate_mod_base_weight(m_data)
                # 同样利用聚合函数拿动态动作
                # 这样可以确保动态规则的全局开关在这里也能生效
                raw_constraints = self.rule_mgr.collect_constraints(mid, m_data)
                
                for c in raw_constraints:
                    if c['type'] == 'dynamic':
                        act = c['action']
                        if act['type'] == 'weight_shift': w += act['value']
                        elif act['type'] == 'weight_set': w = act['value']
                        elif act['type'] == 'top': w = 0
                        elif act['type'] == 'bottom': w = 1000
                weights.append(w)
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
        # 在 Kahn 算法的 PriorityQueue 中，我们希望早出来的权重小。
        # 这里的 propagate 逻辑可以保留之前的，或者简化。
        # 原逻辑：child 的权重小于 parent，则 parent 权重降级。
        # adj[u] = {v: w} 表示 u -> v，即 u 在前。
        # 如果 effective_weights[v] (后) < effective_weights[u] (前)
        # 这是“汉化包置底(900) -> Core(0)”的情况？通常不会发生。
        # 通常是 Core(0) -> Mod(500)。
        # 这里保留原逻辑以防万一。
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
        all_auto_activated = []
        for g in sorted_groups:
            final_list.extend(g.mod_ids)
            all_auto_activated.extend(g.auto_activated)

        return {
            "sorted_ids": final_list,
            "auto_activated": all_auto_activated,
            "warnings": cycle_warnings # 包含冲突消解的日志
        }
    
    
    
