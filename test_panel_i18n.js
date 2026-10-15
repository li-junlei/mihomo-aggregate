const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('panel-i18n.js', 'utf8');
function runtime(saved, languages, blocked = false) {
  const storage = new Map(saved ? [['panel-language', saved]] : []);
  const context = vm.createContext({navigator: {languages}, localStorage: {
    getItem: key => { if (blocked) throw Error('Storage blocked'); return storage.get(key); },
    setItem: (key, value) => { if (blocked) throw Error('Storage blocked'); storage.set(key, value); },
  }});
  vm.runInContext(source, context);
  return {i18n: vm.runInContext('PanelI18n', context), storage};
}
const {i18n, storage} = runtime(null, ['en-US']);
assert.equal(i18n.locale, 'en');
assert.equal(i18n.t('仪表盘'), 'Dashboard');
assert.equal(i18n.t('当前匹配 {count} 个节点', {count: 12}), 'Currently matches 12 nodes');
assert.equal(i18n.t('请求来源无效'), 'Invalid request origin');
assert.equal(i18n.t('unknown error'), 'unknown error');
assert.equal(i18n.country('🇭🇰 香港'), '🇭🇰 Hong Kong');
assert.equal(i18n.country('🌐 其他地区'), '🌐 Other regions');
assert.equal(i18n.country('ss'), 'ss');
i18n.setLocale('zh-CN');
assert.equal(storage.get('panel-language'), 'zh-CN');
assert.equal(i18n.t('当前匹配 {count} 个节点', {count: 2}), '当前匹配 2 个节点');
assert.equal(i18n.country('🇭🇰 香港'), '🇭🇰 香港');
assert.equal(runtime('en', ['zh-CN']).i18n.locale, 'en');
assert.equal(runtime('invalid', ['fr', 'en-GB']).i18n.locale, 'en');
assert.equal(runtime(null, ['zh-TW']).i18n.locale, 'zh-CN');
assert.equal(runtime(null, ['de']).i18n.locale, 'zh-CN');
const blocked = runtime(null, ['en'], true).i18n;
blocked.setLocale('zh-CN');
assert.equal(blocked.locale, 'zh-CN');

// Every marked HTML string and literal translation key must have an English entry.
const html = fs.readFileSync('panel.html', 'utf8');
const en = JSON.parse(source.match(/const en = (\{[\s\S]*?\n\});/)[1]);
const keys = [...html.matchAll(/data-i18n(?:-aria-label|-title|-placeholder)?="([^"]+)"/g)].map(m => m[1]);
keys.push(...[...html.matchAll(/\bt\('([^']+)'/g)].map(m => m[1]));
for (const key of keys) assert.ok(Object.hasOwn(en, key), `Missing English translation: ${key}`);
console.log('Panel language detection, storage, translation and coverage tests passed');
