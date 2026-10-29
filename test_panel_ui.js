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
  t: key => key,
  PanelI18n: {locale: 'zh-CN'},
});
for (const name of ['ruleMatches', 'reason', 'selectNodes', 'setExclusions', 'reorderSource', 'date', 'bytes']) {
  const line = script.split('\n').find(line => line.startsWith(`function ${name}(`) || line.startsWith(`async function ${name}(`));
  assert.ok(line, `Missing ${name}`);
  vm.runInContext(line, context);
}
assert.equal(context.date(null), '未提供');
assert.equal(context.bytes(null), '未提供');
assert.equal(context.bytes(1024), '1.00 KiB');
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

// File subscriptions retain their content when reopened and clear URL-only fields.
const fields = Object.fromEntries(['subscriptionType','fileFields','urlFields','sourceUrl','fileInfo','sourceName','sourceId','website','proxy','ua','enabled'].map(id => [id,{value:'',checked:true}]));
Object.assign(fields.subscriptionType,{value:'file'});
fields.sourceUrl.value='https://example.com/private';fields.proxy.value='http://localhost:7890';
const fileContext=vm.createContext({$:id=>fields[id],cfg:{sources:[]},editing:-1,uploadedYaml:'proxies: []',uploadedName:'nodes.yaml',t:key=>key});
for(const name of ['subscriptionFields','draft'])vm.runInContext(script.split('\n').find(line=>line.startsWith(`function ${name}(`)),fileContext);
fileContext.subscriptionFields();
assert.equal(fields.sourceUrl.required,false);assert.equal(fields.urlFields.hidden,true);assert.equal(fields.fileFields.hidden,false);
assert.equal(fileContext.draft().yaml_content,'proxies: []');assert.equal(fileContext.draft().url,'');assert.equal(fileContext.draft().fetch_proxy,'');
fields.subscriptionType.value='url';fileContext.subscriptionFields();
assert.equal(fields.sourceUrl.required,true);assert.equal(fields.fileFields.hidden,true);assert.equal(fileContext.draft().yaml_content,'');assert.equal(fileContext.draft().url,fields.sourceUrl.value);
console.log('File subscription fields and draft tests passed');

const messages=JSON.parse(script.match(/const logMessages=(\{[^\n]+\});/)[1]);
const logContext=vm.createContext({cfg:{sources:[{id:'sanyuan',name:'三元店'}]},logMessages:messages,date:()=> 'now',t:(key,args={})=>key.replace(/\{(\w+)\}/g,(_,key)=>args[key])});
vm.runInContext(script.split('\n').find(line=>line.startsWith('function logLine(')),logContext);
assert.ok(logContext.logLine({time:1,service:'worker',source_id:'sanyuan',event:'probe_progress',done:10,total:92,healthy:7}).includes('三元店] 检测进度 10/92，可用 7'));
assert.ok(logContext.logLine({time:1,service:'worker',event:'task_failed',error:'ValueError'}).endsWith('任务失败 · ValueError'));
for(const key of Object.values(messages)){assert.ok(Object.hasOwn(JSON.parse(fs.readFileSync('panel-i18n.js','utf8').match(/const en = (\{[\s\S]*?\n\});/)[1]),key),key)}
console.log('Log progress rendering and translation tests passed');

// Node water is a fallback only when both traffic and expiry are absent.
let cardData;
const cardFields = {};
const cardClasses = new Set();
const card = {
  classList: {toggle: (key, on) => on ? cardClasses.add(key) : cardClasses.delete(key)},
  style: {setProperty: (key, value) => {cardFields[key] = value;}},
  querySelector: key => cardFields[key] ||= {},
};
const cardContext = vm.createContext({airportData: () => cardData, t: key => key, bytes: context.bytes, date: context.date});
vm.runInContext(script.split('\n').find(line => line.startsWith('function cardUpdate(')), cardContext);
function updateCard(data, source = {}) {cardData = data; cardContext.cardUpdate(card, {id:'test', ...source});}
updateCard({cached:100, healthy:75, published:80});
assert.ok(cardClasses.has('node-mode'));
assert.equal(cardFields['--level'], '75%');
assert.equal(cardFields['.percent'].textContent, '75%');
assert.equal(cardFields['.traffic'].textContent, '可用节点占比');
assert.equal(cardFields['.healthy-count'].textContent, 75);
assert.equal(cardFields['.expiry'].hidden, true);
updateCard({cached:100, healthy:0});
assert.equal(cardFields['--level'], '0%');
assert.equal(cardFields['.balance'].hidden, false);
for (const data of [{cached:0,healthy:0}, {cached:100,healthy:null}]) {
  updateCard(data);
  assert.equal(cardFields['.balance'].hidden, true);
}
for (const info of [{expires_at:123}, {remaining_bytes:0}, {total_bytes:100}]) {
  updateCard({cached:100,healthy:75,subscription_info:info});
  assert.ok(!cardClasses.has('node-mode'));
  assert.equal(cardFields['.node-metrics'].hidden, true);
}
updateCard({cached:100,healthy:75,subscription_info:{total_bytes:100,remaining_bytes:20}});
assert.equal(cardFields['--level'], '20%');
assert.equal(cardFields['.balance'].hidden, false);
assert.equal(cardFields['.expiry'].hidden, false);
updateCard({cached:100,healthy:75,published:80}, {enabled:false});
assert.equal(cardFields['.published-count'].textContent, 0);
assert.ok(cardClasses.has('disabled'));
console.log('Card node water fallback tests passed');

(async()=>{
  const fields = Object.fromEntries(['saveEmail','emailEnabled','email_host','email_port','email_security','email_username','email_password','email_sender','email_recipient'].map(id=>[id,{value:''}]));
  Object.assign(fields.emailEnabled,{checked:true});
  for(const [key,value] of Object.entries({host:'smtp.example.com',port:'587',security:'starttls',username:'user',password:'secret',sender:'from@example.com',recipient:'to@example.com'}))fields['email_'+key].value=value;
  let savedEmail;
  const emailCfg={sources:[]};
  const emailContext=vm.createContext({cfg:emailCfg,$:id=>fields[id],structuredClone,notice:message=>{throw Error(message)},saveConfig:async next=>{savedEmail=structuredClone(next);emailContext.cfg=next}});
  vm.runInContext(script.split('\n').find(line=>line.startsWith("$('saveEmail').onclick=")),emailContext);
  await fields.saveEmail.onclick();
  assert.equal(savedEmail.email.password,'secret');
  assert.equal(savedEmail.email.port,587);
  assert.equal(savedEmail.email.security,'starttls');
  assert.equal(emailContext.cfg.email.password,undefined);
  assert.equal(fields.email_password.value,'');
  await fields.saveEmail.onclick();
  assert.equal(Object.hasOwn(savedEmail.email,'password'),false);
  assert.equal(fields.saveEmail.disabled,false);
  console.log('Email settings save and password retention UI tests passed');
})().catch(error=>{console.error(error);process.exitCode=1});
