import assert from 'node:assert/strict'
import test from 'node:test'
import { effectScope, reactive } from 'vue'
import { useModListQuery } from '../src/features/mod/list/useModListQuery.js'

const setup = (t, listId = 'active') => {
  const mods = reactive({
    z: { name: 'Zulu', alias_name: 'Alpha', display_name: '000' },
    a: { name: 'Alpha', alias_name: 'Zulu' },
    m: { name: 'Middle', alias_name: '' },
    b: { name: 'Bravo' },
  })
  const props = reactive({ listId, modelValue: ['z', 'a', 'm', 'b'] })
  const scope = effectScope()
  t.after(() => scope.stop())
  const query = scope.run(() => useModListQuery({
    props, appStore: { settings: { ui: {} }, scalePx: value => value },
    modStore: { takeModById: id => mods[id] }, searchStore: {}, toast: {},
    normalizeTokenId: value => value, normalizeCanonicalId: value => value,
  }))
  return { mods, props, query }
}

test('name ordering prefers aliases in active, inactive and temporary lists', t => {
  for (const listId of ['active', 'inactive', 'temp']) {
    const { props, query } = setup(t, listId)
    query.sortMode.value = 'name'
    assert.deepEqual(query.displayList.value, ['z', 'b', 'm', 'a'])
    query.isSortAsc.value = false
    assert.deepEqual(query.displayList.value, ['a', 'm', 'b', 'z'])
    assert.deepEqual(props.modelValue, ['z', 'a', 'm', 'b'])
    assert.equal(query.allowSort.value, false)
    query.clearSort()
    assert.deepEqual(query.displayList.value, props.modelValue)
    assert.equal(query.allowSort.value, true)
  }
})

test('original name ordering ignores aliases and display names in both directions', t => {
  const { mods, query } = setup(t)
  query.sortMode.value = 'original_name'
  assert.deepEqual(query.displayList.value, ['a', 'b', 'm', 'z'])
  mods.a.alias_name = '000'
  mods.z.alias_name = 'zzz'
  assert.deepEqual(query.displayList.value, ['a', 'b', 'm', 'z'])
  query.isSortAsc.value = false
  assert.deepEqual(query.displayList.value, ['z', 'm', 'b', 'a'])
  assert.ok(query.SORT_MENU_GROUPS.value[0].items.includes('original_name'))
  assert.equal(query.SORT_MODE_MAP.value.original_name, '原名')
})

test('editing or clearing an alias immediately updates name ordering', t => {
  const { mods, query } = setup(t)
  query.sortMode.value = 'name'
  assert.equal(query.displayList.value[0], 'z')
  mods.z.alias_name = 'Zzzz'
  assert.equal(query.displayList.value.at(-1), 'z')
  mods.a.alias_name = ''
  assert.equal(query.displayList.value[0], 'a')
})

test('both name modes fall back to the list token for missing names or mods', t => {
  const { mods, props, query } = setup(t)
  mods.b.name = ''
  props.modelValue = ['d', 'b']
  for (const mode of ['name', 'original_name']) {
    query.sortMode.value = mode
    assert.deepEqual(query.displayList.value, ['b', 'd'])
  }
})
