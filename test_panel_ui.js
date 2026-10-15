const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const script = fs.readFileSync('panel.html', 'utf8').split('<script>')[1].split('</script>')[0];
new vm.Script(script);
const config = {sources: [{id: 'a'}, {id: 'b'}], exclude_rules: []};
let saved;
const context = vm.createContext({
  cfg: config,
  structuredClone,
  saveConfig: async next => { saved = next; },
  notice: () => {},
});
for (const name of ['ruleMatches', 'reason', 'selectNodes', 'setExclusions', 'reorderSource']) {
  const line = script.split('\n').find(line => line.startsWith(`function ${name}(`) || line.startsWith(`async function ${name}(`));
  assert.ok(line, `Missing ${name}`);
  vm.runInContext(line, context);
}
const nodes = [
  {id:'1',source_id:'a',name:'Hong Kong',country:'HK',type:'ss',delay_ms:50,healthy:true,enabled:true},
  {id:'2',source_id:'a',name:'Japan',country:'JP',type:'trojan',delay_ms:null,healthy:false,enabled:true},
  {id:'3',source_id:'b',name:'Hong Kong',country:'HK',type:'ss',delay_ms:20,healthy:true,enabled:false},
];
const filters = {search:'',airport:[],country:[],protocol:[],state:[],sort:'name'};
assert.equal(context.selectNodes(nodes, {...filters,search:'HONG'}).length, 2);
assert.equal(context.selectNodes(nodes, {...filters,country:["HK"],airport:["a"]}).length, 1);
assert.equal(context.selectNodes(nodes, {...filters,state:["failed"]})[0].id, '2');
assert.equal(context.selectNodes(nodes, {...filters,state:['unexcluded']}).length, 3);
assert.equal(context.selectNodes(nodes, {...filters,state:["unknown"]}).length, 0);
assert.equal(context.selectNodes(nodes, {...filters,protocol:["trojan"]})[0].id, '2');
assert.equal(context.selectNodes(nodes, {...filters,sort:'delay'})[2].id, '2');
assert.equal(context.selectNodes(nodes, {...filters,search:'absent'}).length, 0);
assert.equal(context.selectNodes(nodes,{...filters,country:['HK','JP'],airport:['a'],state:['healthy','failed']}).length,2);
assert.equal(context.selectNodes(nodes,{...filters,protocol:['ss','trojan']}).length,3);
config.exclude_rules.push({source_id:'a',name_contains:'hong'});
assert.equal(context.reason(nodes[0]), 'rule');
assert.equal(context.reason(nodes[2]), null);
config.exclude_rules[0].enabled=false;
assert.equal(context.reason(nodes[0]),null);
config.exclude_unhealthy=true;
assert.equal(context.reason(nodes[1]),'rule');
assert.equal(context.reason({...nodes[1],healthy:null}),null);
assert.equal(context.selectNodes(nodes,{...filters,state:['unexcluded']}).length,2);
config.exclude_unhealthy=false;
config.exclude_rules = [];
const uk = {source_id:'b',name:'UK premium',country:'🇬🇧 英国',type:'vless'};
assert.equal(context.ruleMatches(uk,{country:'🇬🇧 英国',protocol:'vless'}),true);
assert.equal(context.ruleMatches({...uk,type:'ss'},{country:'🇬🇧 英国',protocol:'vless'}),false);
assert.equal(context.ruleMatches({...uk,country:'🇯🇵 日本'},{country:'🇬🇧 英国',protocol:'vless'}),false);
assert.equal(context.ruleMatches(uk,{source_id:'a',country:'🇬🇧 英国'}),false);
assert.equal(context.ruleMatches(uk,{name_contains:'PREMIUM',country:'🇬🇧 英国'}),true);
(async () => {
  context.saving = false;
  context.document = {querySelectorAll: () => []};
  await context.reorderSource('a', 'b');
  assert.deepEqual(JSON.parse(JSON.stringify(saved.sources.map(s=>s.id))), ['b','a']);
  assert.deepEqual(config.sources.map(s=>s.id), ['a','b'], 'Save failure must preserve the original order');
  const previousSave = saved;
  await context.reorderSource('missing', 'a');
  await context.reorderSource('a', 'a');
  assert.equal(saved, previousSave);
  const selected = context.selectNodes(nodes, {...filters,country:["HK"]});
  await context.setExclusions(selected, true);
  assert.deepEqual(JSON.parse(JSON.stringify(saved.sources.map(s=>s.excluded_nodes))), [['1'],['3']]);
  assert.equal(config.sources[0].excluded_nodes, undefined, 'Failed saves must not change the current config');
  context.cfg = saved;
  assert.equal(context.selectNodes(nodes, {...filters,state:["excluded"]}).length, 2);
  await context.setExclusions([nodes[0]], false);
  assert.deepEqual(JSON.parse(JSON.stringify(saved.sources.map(s=>s.excluded_nodes))), [[],['3']]);
  context.cfg=saved;
  context.cfg.exclude_rules=[{country:'HK'}];
  await context.setExclusions(selected,false);
  assert.deepEqual(JSON.parse(JSON.stringify(saved.sources.map(s=>s.excluded_nodes))), [[],[]]);
  assert.deepEqual(JSON.parse(JSON.stringify(saved.exclude_rules)),[{country:'HK'}]);
  context.cfg=saved;
  assert.equal(context.reason(nodes[2]),'rule','Bulk restoration must preserve persistent exclusions');
  console.log('Panel filtering and batch exclusion tests passed');
})().catch(error => { console.error(error); process.exitCode=1; });
