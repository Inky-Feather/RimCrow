import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { toast, checkResult } from '../../shared/lib/common'

const createEmptyOverview = () => ({
  summary: {
    group_count: 0,
    item_count: 0,
    directory_count: 0,
    settings_file_count: 0,
    total_size: 0,
    file_count: 0,
    whitelist_count: 0,
  },
  groups: [],
  whitelist: [],
  scan_roots: [],
})

export const useModResidueStore = defineStore('modResidue', () => {
  const overview = ref(createEmptyOverview())
  const loading = ref(false)

  const groups = computed(() => overview.value?.groups || [])
  const whitelist = computed(() => overview.value?.whitelist || [])
  const summary = computed(() => overview.value?.summary || createEmptyOverview().summary)
  const hasResidue = computed(() => Number(summary.value.item_count || 0) > 0)

  const setOverview = (data) => {
    overview.value = data && typeof data === 'object' ? data : createEmptyOverview()
  }

  const loadOverview = async ({ silent = false } = {}) => {
    if (!window.pywebview?.api?.mod_residue_get_overview) return null
    loading.value = true
    try {
      const res = await window.pywebview.api.mod_residue_get_overview()
      if (!checkResult(res, '读取卸载残留列表', false, { silent })) return null
      setOverview(res.data || createEmptyOverview())
      return overview.value
    } finally {
      loading.value = false
    }
  }

  const addWhitelist = async (paths) => {
    if (!window.pywebview?.api?.mod_residue_whitelist_add) return false
    const res = await window.pywebview.api.mod_residue_whitelist_add(paths)
    if (!checkResult(res, '加入白名单')) return false
    setOverview(res.data?.overview || overview.value)
    toast.success('已加入白名单，之后扫描会跳过它')
    return true
  }

  const removeWhitelist = async (paths) => {
    if (!window.pywebview?.api?.mod_residue_whitelist_remove) return false
    const res = await window.pywebview.api.mod_residue_whitelist_remove(paths)
    if (!checkResult(res, '移出白名单')) return false
    setOverview(res.data?.overview || overview.value)
    toast.success('已移出白名单，之后扫描会再次提示它')
    return true
  }

  return {
    overview, groups, whitelist, summary, hasResidue, loading,
    setOverview, loadOverview, addWhitelist, removeWhitelist,
  }
})
