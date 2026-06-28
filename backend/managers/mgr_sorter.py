from typing import List, Dict, Tuple
import heapq
from collections import deque, defaultdict
from backend.database.dao import ModDAO
from backend.database.models import ModInterlock
from backend.managers.mgr_profile import ProfileContext
from backend.utils.logger import logger
from backend.settings import settings
from backend.managers.mgr_rules import RuleManager
from backend.load_order.language_pack_ownership import resolve_language_pack_ownership_for_mods


class AtomicGroup:
    """原子组对象：联锁 Mod 的最小单位"""
    def __init__(self, mod_ids: List[str]):
        self.mod_ids = mod_ids  # 组内有序的 Mod ID 列表
        self.is_chain = len(mod_ids) > 1
        self.auto_activated = [] # 记录哪些是因联锁被强制补全的

    def __repr__(self):
        return f"<AtomicGroup chain={self.is_chain} ids={self.mod_ids}>"
    
class OrderSorter:
    # 自动排序策略说明：
    # 1. 名称和描述是直接给用户看的，要尽量说“会排成什么样”，而不是说算法名词。
    # 2. 键名会写入配置文件，所以也尽量保持语义清晰，避免以后看到值却不知道代表什么。
    SORT_STRATEGIES = {
        "classic_sort_logic": {
            "label": "经典自动排序（旧版）",
            "description": "旧版本的自动排序习惯。对置顶/置底、依赖链和联锁组的牵引更保守，通常更稳定、更接近传统手工整理结果。",
        }, 
        "edge_enhanced_sort_logic": {
            "label": "两端强化排序（新版）",
            "description": "更强调置顶/置底的整体牵引。只要模组或联锁组带有明显的置顶/置底倾向，相关模组会更积极地被推向前后两端，结果通常更强烈。",
        },
    }
    DEFAULT_SORT_STRATEGY = "classic_sort_logic"

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

    def _propagate_weights_classic_sort_logic(self, adj: Dict[int, Dict[int, int]], group_base_weights: Dict[int, int]) -> Dict[int, int]:
        """
        经典兼容排序（旧版）的权重传播：
        如果 A 必须在 B 前，而 B 自身权重更靠前，
        就把 A 拉到和 B 一样靠前，避免 A 显得“过重”。
        """
        effective_weights = group_base_weights.copy()
        changed = True
        while changed:
            changed = False
            for u in adj:
                for v in adj[u]:
                    if effective_weights[v] < effective_weights[u]:
                        effective_weights[u] = effective_weights[v]
                        changed = True
        return effective_weights

    def _get_tail_sizes_edge_enhanced_sort_logic(self, adj: Dict[int, Dict[int, int]], group_ids: List[int]) -> Dict[int, int]:
        """
        计算每个节点能向后覆盖多长的依赖尾巴。
        注意这只是“节点自身”的局部尾长。
        后续新版真正用于比较的，是“所属置底锚点”的尾长，它会再沿链向后传播。
        """
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

        return {gid: get_tail_size(gid) for gid in group_ids}

    def _get_head_sizes_edge_enhanced_sort_logic(self, adj: Dict[int, Dict[int, int]], group_ids: List[int]) -> Dict[int, int]:
        """
        计算每个节点向前能覆盖多长的依赖头部。
        这里的“头”指所有必须排在它前面的前驱链。
        和尾长一样，这里先算节点自身的局部头长，后续再把置顶锚点的头长沿链向前传播。
        """
        reverse_adj = defaultdict(list)
        for u, neighbors in adj.items():
            for v in neighbors:
                reverse_adj[v].append(u)

        head_size_cache = {}

        def get_head_size(start_node_id):
            if start_node_id in head_size_cache:
                return head_size_cache[start_node_id]
            q = deque([start_node_id])
            visited = {start_node_id}
            count = 0
            while q:
                curr_id = q.popleft()
                count += 1
                for prev_id in reverse_adj.get(curr_id, []):
                    if prev_id not in visited:
                        visited.add(prev_id)
                        q.append(prev_id)
            head_size_cache[start_node_id] = count
            return count

        return {gid: get_head_size(gid) for gid in group_ids}

    def _propagate_weights_edge_enhanced_sort_logic(
        self,
        adj: Dict[int, Dict[int, int]],
        classic_effective_weights: Dict[int, int],
        group_anchor_flags: Dict[int, Dict[str, bool]],
        all_head_sizes: Dict[int, int],
        all_tail_sizes: Dict[int, int],
        groups_map: Dict[int, AtomicGroup],
    ) -> Tuple[Dict[int, int], Dict[int, int], Dict[int, int], set[int], set[int], List[dict]]:
        """
        两端强化排序（新版）的闭包传播：
        1. 先以经典排序结果作为普通节点的基线权重。
        2. 仅将纯置顶闭包推向最前、纯置底闭包压向最后。
        3. 同时落在置顶/置底闭包中的普通节点，不直接升成极值，只保留依赖约束并给出提示。
        """
        propagated_top_head_sizes = {}
        propagated_top_distances = {}
        propagated_bottom_tail_sizes = {}
        propagated_bottom_distances = {}
        promoted_top_ids = set()
        promoted_bottom_ids = set()
        warnings = []

        for gid, anchor_flags in group_anchor_flags.items():
            if anchor_flags.get("top"):
                propagated_top_head_sizes[gid] = all_head_sizes.get(gid, 1)
                propagated_top_distances[gid] = 0
            if anchor_flags.get("bottom"):
                propagated_bottom_tail_sizes[gid] = all_tail_sizes.get(gid, 1)
                propagated_bottom_distances[gid] = 0

        for _ in range(len(groups_map) + 1):
            changed = False
            for u, neighbors in adj.items():
                for v in neighbors:
                    # 置顶链沿反方向传播：v 被置顶，则排在它前面的 u 也应该被一起顶上去。
                    if v in propagated_top_head_sizes:
                        candidate_head_size = propagated_top_head_sizes[v]
                        candidate_distance = propagated_top_distances[v] + 1
                        current_head_size = propagated_top_head_sizes.get(u)
                        current_distance = propagated_top_distances.get(u, 10**9)
                        if current_head_size is None or candidate_head_size < current_head_size or (candidate_head_size == current_head_size and candidate_distance < current_distance):
                            propagated_top_head_sizes[u] = candidate_head_size
                            propagated_top_distances[u] = candidate_distance
                            changed = True

                    # 置底链沿正方向传播：u 被置底，则依赖它的 v 也应该被一起压下去。
                    if u in propagated_bottom_tail_sizes:
                        candidate_tail_size = propagated_bottom_tail_sizes[u]
                        candidate_distance = propagated_bottom_distances[u] + 1
                        current_tail_size = propagated_bottom_tail_sizes.get(v)
                        current_distance = propagated_bottom_distances.get(v, 10**9)
                        if current_tail_size is None or candidate_tail_size < current_tail_size or (candidate_tail_size == current_tail_size and candidate_distance < current_distance):
                            propagated_bottom_tail_sizes[v] = candidate_tail_size
                            propagated_bottom_distances[v] = candidate_distance
                            changed = True
            if not changed:
                break

        effective_weights = classic_effective_weights.copy()
        for gid, base_weight in classic_effective_weights.items():
            anchor_flags = group_anchor_flags.get(gid, {})
            is_top_anchor = anchor_flags.get("top", False)
            is_bottom_anchor = anchor_flags.get("bottom", False)
            in_top_chain = gid in propagated_top_head_sizes
            in_bottom_chain = gid in propagated_bottom_tail_sizes

            if is_top_anchor and is_bottom_anchor:
                group_name = groups_map[gid].mod_ids[0]
                warnings.append({
                    "type": "edge_anchor_conflict",
                    "level": "warn",
                    "message": f"[{group_name}] 同时被要求置顶和置底，这两个要求互相冲突。系统这次不会强行把它放到最前或最后，只会先保证依赖顺序正确。"
                })
                continue

            if is_top_anchor:
                effective_weights[gid] = 0
                promoted_top_ids.add(gid)
                if in_bottom_chain:
                    group_name = groups_map[gid].mod_ids[0]
                    warnings.append({
                        "type": "edge_anchor_overlap",
                        "level": "warn",
                        "message": f"[{group_name}] 被要求置顶，但它关联的一串模组里又碰到了置底要求。系统这次先保留它的置顶，其它受影响模组改为按依赖关系尽量排好。"
                    })
                continue

            if is_bottom_anchor:
                effective_weights[gid] = 10000
                promoted_bottom_ids.add(gid)
                if in_top_chain:
                    group_name = groups_map[gid].mod_ids[0]
                    warnings.append({
                        "type": "edge_anchor_overlap",
                        "level": "warn",
                        "message": f"[{group_name}] 被要求置底，但它关联的一串模组里又碰到了置顶要求。系统这次先保留它的置底，其它受影响模组改为按依赖关系尽量排好。"
                    })
                continue

            if in_top_chain and not in_bottom_chain:
                effective_weights[gid] = 0
                promoted_top_ids.add(gid)
            elif in_bottom_chain and not in_top_chain:
                effective_weights[gid] = 10000
                promoted_bottom_ids.add(gid)
            elif in_top_chain and in_bottom_chain:
                group_name = groups_map[gid].mod_ids[0]
                warnings.append({
                    "type": "edge_closure_conflict",
                    "level": "warn",
                    "message": f"[{group_name}] 同时被置顶链和置底链夹住了，两边要求打架。系统不会把它强行推到最前或最后，而是先保证依赖顺序正确，再放到尽量合适的位置。"
                })

        return (
            effective_weights,
            propagated_top_head_sizes,
            propagated_bottom_tail_sizes,
            promoted_top_ids,
            promoted_bottom_ids,
            warnings,
        )

    def _is_language_pack_group(self, group: AtomicGroup, mod_map: Dict[str, dict]) -> bool:
        """判断一个原子组是否整体属于语言包。"""
        if not group.mod_ids:
            return False
        for mid in group.mod_ids:
            mod_data = mod_map.get(mid, {})
            mod_type = str(mod_data.get('user_mod_type') or mod_data.get('mod_type') or '').strip()
            if mod_type != 'LanguagePack':
                return False
        return True

    def _get_group_target_predecessors(self, group: AtomicGroup, mod_to_group: Dict[str, AtomicGroup]) -> set[int]:
        """提取语言包组声明的直接前置/依赖目标。"""
        target_gids = set()
        for mid in group.mod_ids:
            mod_data = getattr(self, "mod_map", {}).get(mid, {})
            owner_result = mod_data.get("language_pack_owner_result") or {}
            owner_confidence = str(owner_result.get("summary_confidence") or "").strip().lower()
            used_high_confidence_owner_result = False
            if owner_confidence == "high":
                used_high_confidence_owner_result = True
                for owner in owner_result.get("owners", []) or []:
                    target_id = str(owner.get("package_id") or "").strip().lower()
                    if not target_id or target_id not in mod_to_group:
                        continue
                    target_group = mod_to_group[target_id]
                    target_gid = id(target_group)
                    if target_gid != id(group):
                        target_gids.add(target_gid)
                # 只要已经存在高置信归属结果，就不要再退回旧的 dependencies/load_after。
                # 否则当原模组未启用时，旧规则里的 Core/DLC/框架前置会把语言包错误拉到列表前部。
                if used_high_confidence_owner_result:
                    continue
            rules = self.effective_rules_cache.get(mid, {})
            # 对语言包来说，dependencies 与 load_after 都表示“它应该跟在这些目标之后”。
            for relation in [*(rules.get('dependencies', []) or []), *(rules.get('load_after', []) or [])]:
                target_id = str(relation.get('target_id') or '').strip().lower()
                if not target_id or target_id not in mod_to_group:
                    continue
                target_group = mod_to_group[target_id]
                target_gid = id(target_group)
                if target_gid != id(group):
                    target_gids.add(target_gid)
        return target_gids

    def _tighten_language_pack_groups(
        self,
        sorted_groups: List[AtomicGroup],
        adj: Dict[int, Dict[int, int]],
        mod_map: Dict[str, dict],
        mod_to_group: Dict[str, AtomicGroup],
        group_anchor_flags: Dict[int, Dict[str, bool]],
    ) -> Tuple[List[AtomicGroup], List[dict]]:
        """
        可选后处理：让语言包尽量贴在其最后一个前置/依赖模组后方。
        只在不破坏现有拓扑约束时移动。
        """
        if not getattr(settings.config, "language_packs_follow_targets", False):
            return sorted_groups, []

        order = list(sorted_groups)
        warnings = []
        reverse_adj = defaultdict(set)
        for u, neighbors in adj.items():
            for v in neighbors:
                reverse_adj[v].add(u)

        candidate_groups = [g for g in order if self._is_language_pack_group(g, mod_map)]
        for group in candidate_groups:
            gid = id(group)
            group_name = group.mod_ids[0]
            anchor_flags = group_anchor_flags.get(gid, {})
            if anchor_flags.get("top") or anchor_flags.get("bottom"):
                continue

            predecessor_targets = self._get_group_target_predecessors(group, mod_to_group)
            if not predecessor_targets:
                continue

            positions = {id(g): idx for idx, g in enumerate(order)}
            current_pos = positions.get(gid)
            if current_pos is None:
                continue

            predecessor_positions = [positions[pred_gid] for pred_gid in predecessor_targets if pred_gid in positions]
            if not predecessor_positions:
                continue
            # 目标位置定义为“最后一个前置/依赖目标的后一格”。
            latest_predecessor_pos = max(predecessor_positions)
            desired_pos = latest_predecessor_pos + 1
            if desired_pos >= current_pos:
                continue

            direct_successors = [positions[succ_gid] for succ_gid in adj.get(gid, {}) if succ_gid in positions]
            earliest_successor_pos = min(direct_successors) if direct_successors else len(order)
            if desired_pos >= earliest_successor_pos:
                blocker_gid = min((succ_gid for succ_gid in adj.get(gid, {}) if succ_gid in positions), key=lambda x: positions[x], default=None)
                blocker_name = group.mod_ids[0]
                if blocker_gid is not None:
                    blocker_group = next((g for g in order if id(g) == blocker_gid), None)
                    blocker_name = blocker_group.mod_ids[0] if blocker_group else blocker_name
                warnings.append({
                    "type": "language_pack_follow_blocked",
                    "level": "warn",
                    "message": f"语言包 [{group_name}] 想贴到最后一个前置后面，但再往前会压过它后面必须依赖的模组 [{blocker_name}]。系统已保留当前顺序以避免破坏规则。"
                })
                continue

            # 额外稳妥：不能越过任何直接前驱，也不能压到任何直接后继之后。
            # 这一步是“贴边”成立的关键：它允许我们在不破坏拓扑合法性的前提下，做一次局部上提。
            direct_predecessor_positions = [positions[pred_gid] for pred_gid in reverse_adj.get(gid, set()) if pred_gid in positions]
            if direct_predecessor_positions and desired_pos <= max(direct_predecessor_positions):
                desired_pos = max(direct_predecessor_positions) + 1
            if desired_pos >= earliest_successor_pos or desired_pos >= current_pos:
                blocker_gid = max((pred_gid for pred_gid in reverse_adj.get(gid, set()) if pred_gid in positions), key=lambda x: positions[x], default=None)
                blocker_name = group.mod_ids[0]
                if blocker_gid is not None:
                    blocker_group = next((g for g in order if id(g) == blocker_gid), None)
                    blocker_name = blocker_group.mod_ids[0] if blocker_group else blocker_name
                warnings.append({
                    "type": "language_pack_follow_blocked",
                    "level": "warn",
                    "message": f"语言包 [{group_name}] 想贴到最后一个前置后面，但中间还有必须排在它前面的模组 [{blocker_name}]。系统已保留当前顺序以避免破坏规则。"
                })
                continue

            moved_group = order.pop(current_pos)
            order.insert(desired_pos, moved_group)

        return order, warnings

    def sort(self, active_ids: List[str], strategy: str | None = None):
        """
        最终排序：原子组 -> 权重修正 -> 依赖构图 -> 权重传播 -> 拓扑排序 (带名称稳定性)
        """
        strategy = str(strategy or getattr(settings.config, "auto_sort_strategy", self.DEFAULT_SORT_STRATEGY) or self.DEFAULT_SORT_STRATEGY).strip()
        if strategy not in self.SORT_STRATEGIES:
            strategy = self.DEFAULT_SORT_STRATEGY
        logger.info(f"Starting sort for {len(active_ids)} mods with strategy={strategy}...")
        all_mods_data = ModDAO.get_profile_mods(self.context)
        # all_mods_data = ModDAO.get_profile_mods(self.context or None)
        mod_map = {m['package_id'].lower(): m for m in all_mods_data}
        self.mod_map = mod_map
        current_assets_ids = list(mod_map.keys())
        from backend.database.dao import GroupDAO
        all_groups = GroupDAO.get_groups_structured_by_mod_ids(current_assets_ids) or []
        if not isinstance(all_groups, list):
            try:
                all_groups = list(all_groups)
            except TypeError:
                all_groups = []
        # 建立反向映射: package_id -> [group_name1, group_name2]
        mod_groups_map = defaultdict(list)
        for g in all_groups:
            for mid in g['mod_ids']:
                mod_groups_map[mid.lower()].append(g['name'])
        # 将分组名注入到 mod_map 中
        for mid, m_data in mod_map.items():
            m_data['groups'] = mod_groups_map.get(mid, [])

        self.effective_rules_cache = {} # 全局规则缓存字典
        for mid, m_data in mod_map.items():
            self.effective_rules_cache[mid] = self.rule_mgr.get_effective_mod_rules(mid, m_data)
            m_data['rules'] = self.effective_rules_cache[mid]
        language_pack_owner_map = resolve_language_pack_ownership_for_mods(
            list(mod_map.values()),
            user_mod_rules=self.rule_mgr.user_mod_rules,
        )
        for mid, m_data in mod_map.items():
            m_data['language_pack_owner_result'] = language_pack_owner_map.get(
                mid,
                {
                    "owners": [],
                    "analyzed_owners": [],
                    "relation_type": "unknown",
                    "summary_confidence": "unknown",
                    "analyzed_relation_type": "unknown",
                    "analyzed_summary_confidence": "unknown",
                }
            )
        expanded_active_ids = list(active_ids)
        # 1. 将扩展后的激活列表转化为原子组
        groups, interlock_warnings = self.build_atomic_groups(expanded_active_ids, mod_map)
        mod_to_group = {mid: g for g in groups for mid in g.mod_ids}
        group_ids = [id(g) for g in groups]
        groups_by_id = {id(g): g for g in groups}

        # 2. 计算节点自身权重 (Weight Propagation base)
        # 这一段属于共用外壳：遍历组、取显示名、读取规则缓存。
        # 真正的策略差异只保留在少量分支里。
        classic_group_base_weights = {}
        group_anchor_flags = {}
        group_sort_keys = {}  # 存储 (Name, PackageID) 用于稳定排序
        for g in groups:
            weights = []
            is_top = False
            is_bottom = False
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
                if not isinstance(weight_info, dict): weight_info = {}
                w = weight_info.get("final_weight")
                # 纯粹的算术应用，完全不关心业务逻辑
                if w is None: w = weight_info.get("base_weight", 500) + weight_info.get("weight_shift", 0)
                # 处理决定性的绝对位置
                abs_type = weight_info.get("absolute_type")
                if abs_type == "top": is_top = True  # 标记组内有置顶成员
                elif abs_type == "bottom": is_bottom = True  # 标记组内有置底成员
                w = int(w)
                if w <= 0:
                    is_top = True
                if w >= 10000:
                    is_bottom = True
                weights.append(w)

            # 旧版基线始终只取组内最靠前的一个成员作为整组权重。
            classic_group_base_weights[id(g)] = min(weights) if weights else 500
            group_anchor_flags[id(g)] = {
                "top": is_top,
                "bottom": is_bottom,
            }

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

        # 6. 预计算新版的头/尾长度指标
        all_tail_sizes = {}
        all_head_sizes = {}
        if strategy == "edge_enhanced_sort_logic":
            all_tail_sizes = self._get_tail_sizes_edge_enhanced_sort_logic(adj, group_ids)
            all_head_sizes = self._get_head_sizes_edge_enhanced_sort_logic(adj, group_ids)

        # 7. 权重传播（这里才调用两个策略核心方法）
        if strategy == "classic_sort_logic":
            effective_weights = self._propagate_weights_classic_sort_logic(adj, classic_group_base_weights)
            propagated_top_head_sizes = {}
            propagated_bottom_tail_sizes = {}
            promoted_top_ids = set()
            promoted_bottom_ids = set()
        else:
            classic_effective_weights = self._propagate_weights_classic_sort_logic(adj, classic_group_base_weights)
            (
                effective_weights,
                propagated_top_head_sizes,
                propagated_bottom_tail_sizes,
                promoted_top_ids,
                promoted_bottom_ids,
                edge_warnings,
            ) = self._propagate_weights_edge_enhanced_sort_logic(
                adj,
                classic_effective_weights,
                group_anchor_flags,
                all_head_sizes,
                all_tail_sizes,
                groups_by_id,
            )
            cycle_warnings.extend(edge_warnings)

        # 8. Kahn算法拓扑排序
        # 这里仍然是共用外壳，只在入堆比较键上保留策略差异。
        sorted_groups = []
        queue = []
        work_in_degree = in_degree.copy()

        def push_queue_item(gid: int):
            sort_name, sort_id = group_sort_keys[gid]
            category = 1
            edge_metric = 0
            if strategy == "classic_sort_logic":
                heapq.heappush(queue, (effective_weights[gid], category, edge_metric, sort_name, sort_id, gid))
                return

            if gid in promoted_top_ids:
                category = 0
                edge_metric = int(propagated_top_head_sizes.get(gid, all_head_sizes.get(gid, 1)))
            elif gid in promoted_bottom_ids:
                category = 2
                edge_metric = -int(propagated_bottom_tail_sizes.get(gid, all_tail_sizes.get(gid, 1)))

            heapq.heappush(queue, (effective_weights[gid], category, edge_metric, sort_name, sort_id, gid))

        for gid in group_ids:
            if work_in_degree[gid] == 0:
                push_queue_item(gid)

        while queue:
            gid = heapq.heappop(queue)[-1]
            if gid not in groups_by_id: continue
            g = groups_by_id[gid]
            sorted_groups.append(g)
            if gid in adj:
                for neighbor in adj[gid]:
                    work_in_degree[neighbor] -= 1
                    if work_in_degree[neighbor] == 0:
                        push_queue_item(neighbor)

        # 语言包“贴边”不能只靠主排序权重完成。
        # 原因是 Kahn 拓扑排序一旦把某些无关节点提前出队，就不会再回头把语言包插回它们前面；
        # 因此这里在主排序之后做一次严格受约束的局部调整。
        sorted_groups, language_pack_warnings = self._tighten_language_pack_groups(
            sorted_groups,
            adj,
            mod_map,
            mod_to_group,
            group_anchor_flags,
        )
        cycle_warnings.extend(language_pack_warnings)

        # 10. 兜底检查（虽然已break_cycles，但为了绝对稳健）
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

        # 11. 输出结果
        final_list = []
        interlock_auto_activated  = []
        for g in sorted_groups:
            final_list.extend(g.mod_ids)
            interlock_auto_activated .extend(g.auto_activated)
        
        # 12. 合并自动激活的依赖项，形成最终的自动激活列表
        all_auto_activated = interlock_auto_activated

        return {
            "sorted_ids": final_list,
            "auto_activated": all_auto_activated,
            "warnings": cycle_warnings, # 包含冲突消解的日志
            "strategy": strategy,
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
            # E. 结合权重的精准落位 (附带平级对比机制)
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
                            # [核心修复 2] 权重相同（都是500），引入字母顺序作为对比 (Tie-breaker)
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
        
    
