'use strict';
const $ = id => document.getElementById(id);
let adminKey = '', savedLayout = null, rosterState = null, dirty = false, previewTimer, previewGeneration = 0;
let customFields = [], invite = null, currentPage = 'roster';
const blobCache = new Map();
const base = new URL('./', location.href);
const form = $('layout-form');
const fieldNames = ['title','description','footer','color','mode','inline','order','include_offline','max_players','player_title','player_body','url','author_name','author_url','author_icon','footer_icon','image','thumbnail','timestamp'];
const statNames = ['status','team','scores','connection','updated'];
let statOrder = ['status','team','scores','connection','updated'];

async function api(path, {method='GET', body, raw=false}={}) {
  const headers = {Authorization: 'Bearer ' + adminKey};
  if (body !== undefined) headers['Content-Type'] = raw ? 'application/octet-stream' : 'application/json';
  const response = await fetch(new URL('api/' + path, base), {method, headers, credentials:'omit', redirect:'error', body:body === undefined ? undefined : raw ? body : JSON.stringify(body)});
  if (!response.ok) {
    const problem = await response.json().catch(() => ({detail:'Controller request failed.'}));
    const message = Array.isArray(problem.detail) ? problem.detail.map(v => v.loc.slice(1).join('.') + ': ' + v.msg).join('\n') : problem.detail;
    throw new Error(message || `HTTP ${response.status}`);
  }
  return response.json();
}
function announce(text, bad=false) { $('notice').textContent=text; $('notice').hidden=!text; $('notice').classList.toggle('error',bad); }
function change() { dirty=true; $('dirty').textContent='Unsaved changes'; schedulePreview(); }
function layout() {
  const value={};
  fieldNames.forEach(name => { const input=form.elements.namedItem(name); value[name]=input.type==='checkbox'? input.checked : input.type==='number'? Number(input.value):input.value; });
  value.custom_fields=structuredClone(customFields);
  return value;
}
function loadLayout(value) {
  fieldNames.forEach(name => {const input=form.elements.namedItem(name); if(input.type==='checkbox') input.checked=value[name]; else input.value=value[name];});
  customFields=structuredClone(value.custom_fields||[]); drawFields(); drawStats(); dirty=false; $('dirty').textContent='Saved layout'; schedulePreview();
}
function node(tag, className, text) {const e=document.createElement(tag); if(className)e.className=className; if(text!==undefined)e.textContent=text; return e;}
function action(text, click) {const b=node('button','',text); b.type='button'; b.onclick=click; return b;}

$('login-form').onsubmit=async event => {
  event.preventDefault(); adminKey=$('admin-key').value.trim(); $('login-error').textContent='';
  try { await refresh(true); $('admin-key').value=''; $('login').hidden=true; $('app').hidden=false; }
  catch(error){adminKey='';$('login-error').textContent=error.message;}
};
$('logout').onclick=()=>{adminKey='';previewGeneration++;clearTimeout(previewTimer);blobCache.forEach(URL.revokeObjectURL);blobCache.clear();$('app').hidden=true;$('login').hidden=false;};
document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{
  currentPage=b.dataset.page;
  document.querySelectorAll('[data-page]').forEach(other=>other.classList.toggle('active',other===b));
  $('roster-page').hidden=currentPage!=='roster';$('builder-page').hidden=currentPage!=='builder';
  $('page-title').textContent=currentPage==='roster'?'Players':'Embed builder';
  if(currentPage==='builder')schedulePreview();
});
async function refresh(initial=false) {
  const data=await api('admin/state'); rosterState=data;
  if(initial||!savedLayout){savedLayout=data.layout;loadLayout(savedLayout);}
  const agents=data.agents;
  $('total').textContent=agents.length;$('connected').textContent=agents.filter(p=>p.connection==='connected').length;
  $('playing').textContent=agents.filter(p=>p.connection==='connected'&&p.status.activity==='match').length;
  $('delivery').textContent=data.delivery.dry_run?'Dry run · no Discord sends':data.delivery.error|| (data.delivery.pending?'Update queued':'Discord message up to date');
  $('players').replaceChildren();
  if(!agents.length)$('players').append(node('div','empty','No players yet. Generate your first pairing PIN above.'));
  agents.forEach(player=>{
    const row=node('div','player'), info=node('div'), headline=node('div');
    headline.append(node('strong','',player.username),node('span','connection',player.connection.replaceAll('_',' ')));
    info.append(headline,node('p','muted',player.status.details||player.status.activity));
    if(player.status.team||player.status.scores)info.append(node('div','small muted',[player.status.team,(player.status.scores||[]).join(' / ')].filter(Boolean).join(' · ')));
    const controls=node('div','player-actions');
    controls.append(action(player.enabled?'Disable':'Enable',async()=>{
      try{await api('admin/agents/'+player.id,{method:'PUT',body:{enabled:!player.enabled}});await refresh();}catch(e){announce(e.message,true);}
    }),action('Revoke',async()=>{
      if(!confirm('Revoke '+player.username+'\'s agent credential? They will need a new PIN.'))return;
      try{await api('admin/agents/'+player.id+'/credential',{method:'DELETE'});await refresh();}catch(e){announce(e.message,true);}
    }));row.append(info,controls);$('players').append(row);
  });
  if(currentPage==='builder'&&$('preview-source').value==='live')schedulePreview();
}
setInterval(()=>{if(adminKey)refresh().catch(e=>announce(e.message,true));},10000);
$('pair-form').onsubmit=async event=>{
  event.preventDefault();try{invite=await api('admin/pairings',{method:'POST',body:{username:$('username').value}});$('pair-result').hidden=false;$('pair-name').textContent=invite.username;$('pair-code').textContent=invite.pin;await refresh();}catch(e){announce(e.message,true);}
};
$('copy-invite').onclick=async()=>{try{await navigator.clipboard.writeText(`Controller: ${base.href}\nUsername: ${invite.username}\nPIN: ${invite.pin}\nUse within 10 minutes. This PIN works once.`);announce('Pairing details copied. Share them only with that player.');}catch{announce('Copy the URL, username, and PIN shown above.');}};
form.addEventListener('submit',event=>event.preventDefault());
form.addEventListener('input',event=>{if(event.target.name==='player_body')drawStats();change();});
form.addEventListener('change',change);
document.querySelectorAll('.chips').forEach(box=>box.dataset.vars.split(',').forEach(name=>box.append(action('{'+name+'}',()=>{
  const input=form.elements.namedItem(box.dataset.target), start=input.selectionStart||0,end=input.selectionEnd||0;
  input.value=input.value.slice(0,start)+'{'+name+'}'+input.value.slice(end);input.focus();change();if(box.dataset.target==='player_body')drawStats();
}))));
function drawStats(){
  const target=$('stat-order');target.replaceChildren();
  const included=new Set([...form.elements.player_body.value.matchAll(/\{(\w+)\}/g)].map(m=>m[1]));
  statOrder.forEach((name,index)=>{
    const row=node('div','stat-row');row.draggable=true;
    const check=document.createElement('input');check.type='checkbox';check.checked=included.has(name);check.setAttribute('aria-label','Include '+name);
    const rebuild=()=>{form.elements.player_body.value=[...target.querySelectorAll('input:checked')].map(input=>'{'+input.dataset.stat+'}').join('\n')||'{status}';change();};
    check.dataset.stat=name;check.onchange=rebuild;
    row.append(node('span','','⠿'),check,node('span','',name[0].toUpperCase()+name.slice(1)),action('↑',()=>moveStat(index,-1)),action('↓',()=>moveStat(index,1)));
    row.ondragstart=e=>{e.dataTransfer.setData('text/plain',String(index));};row.ondragover=e=>e.preventDefault();row.ondrop=e=>{e.preventDefault();const from=Number(e.dataTransfer.getData('text/plain'));if(!Number.isInteger(from)||from<0||from>=statOrder.length)return;const item=statOrder.splice(from,1)[0];statOrder.splice(index,0,item);drawStats();form.elements.player_body.value=statOrder.filter(n=>included.has(n)).map(n=>'{'+n+'}').join('\n')||'{status}';change();};
    target.append(row);
  });
}
function moveStat(index, direction){const to=index+direction;if(to<0||to>=statOrder.length)return;const included=new Set([...form.elements.player_body.value.matchAll(/\{(\w+)\}/g)].map(m=>m[1]));[statOrder[index],statOrder[to]]=[statOrder[to],statOrder[index]];form.elements.player_body.value=statOrder.filter(n=>included.has(n)).map(n=>'{'+n+'}').join('\n')||'{status}';drawStats();change();}
function drawFields(){
  const root=$('custom-fields');root.replaceChildren();
  customFields.forEach((field,index)=>{
    const box=node('div','custom-field');
    for(const [key,title] of [['name','Field name'],['value','Field text']]){
      const label=node('label','',title),input=document.createElement(key==='value'?'textarea':'input');input.value=field[key];input.maxLength=key==='value'?1024:256;if(key==='value')input.rows=3;
      input.oninput=()=>{field[key]=input.value;change();};label.append(input);box.append(label);
    }
    const options=node('div','form-row'),position=document.createElement('select');
    [['before','Before players'],['after','After players']].forEach(([v,t])=>{const o=node('option','',t);o.value=v;position.append(o);});position.value=field.position;position.onchange=()=>{field.position=position.value;change();};
    const positionLabel=node('label','','Position');positionLabel.append(position);
    const inline=node('label','check',''),check=document.createElement('input');check.type='checkbox';check.checked=field.inline;check.onchange=()=>{field.inline=check.checked;change();};inline.append(check,document.createTextNode('Inline'));options.append(positionLabel,inline);box.append(options);
    const tools=node('div','field-tools');for(const [text,delta] of [['↑',-1],['↓',1]])tools.append(action(text,()=>{const to=index+delta;if(to<0||to>=customFields.length)return;[customFields[index],customFields[to]]=[customFields[to],customFields[index]];drawFields();change();}));tools.append(action('Remove',()=>{customFields.splice(index,1);drawFields();change();}));box.append(tools);root.append(box);
  });$('add-field').disabled=customFields.length>=20;
}
$('add-field').onclick=()=>{customFields.push({name:'Squad note',value:'Add your message here.',inline:false,position:'after'});drawFields();change();};
document.querySelectorAll('[data-upload]').forEach(input=>input.onchange=async()=>{
  const file=input.files[0];if(!file)return;if(file.size>8*1024*1024){announce('Choose an image up to 8 MB.',true);return;}
  input.disabled=true;
  try{const result=await api('admin/assets',{method:'POST',body:await file.arrayBuffer(),raw:true});form.elements.namedItem(input.dataset.upload).value=result.reference;change();announce('Image uploaded. Publish the layout to attach it to Discord.');}catch(e){announce(e.message,true);}finally{input.disabled=false;input.value='';}
});
document.querySelectorAll('[data-preset]').forEach(button=>button.onclick=()=>{
  const preset=button.dataset.preset;form.elements.mode.value=preset==='cards'?'cards':'compact';form.elements.inline.checked=true;
  form.elements.player_title.value='{icon} {username}';form.elements.player_body.value=preset==='minimal'?'{status}':preset==='compact'?'{status} · {team}\n{scores}':'{status}\n{team}\n{scores}';
  form.elements.max_players.value=preset==='cards'?24:40;drawStats();change();
});
$('reset-layout').onclick=()=>{if(!dirty||confirm('Discard your unsaved layout changes?'))loadLayout(savedLayout);};
$('publish').onclick=async()=>{const button=$('publish');button.disabled=true;try{const value=layout();await api('admin/layout',{method:'PUT',body:value});savedLayout=structuredClone(value);dirty=false;$('dirty').textContent='Saved layout';announce('Layout saved. The shared Discord message will update on the next publishing cycle.');await refresh();}catch(e){announce(e.message,true);}finally{button.disabled=false;}};
$('preview-source').onchange=()=>{$('sample-control').hidden=$('preview-source').value==='live';$('preview-caption').textContent=$('preview-source').value==='live'?'Previewing the current roster.':'Sample data is never published.';schedulePreview();};
$('sample-count').oninput=schedulePreview;
function schedulePreview(){clearTimeout(previewTimer);previewTimer=setTimeout(updatePreview,250);}
async function imageUrl(reference){
  if(!reference)return '';
  if(!reference.startsWith('attachment://'))return reference;
  const name=reference.slice(13);if(blobCache.has(name))return blobCache.get(name);
  const response=await fetch(new URL('api/admin/assets/'+encodeURIComponent(name),base),{headers:{Authorization:'Bearer '+adminKey},credentials:'omit',redirect:'error'});
  if(!response.ok)throw new Error('Could not load an uploaded image.');
  const url=URL.createObjectURL(await response.blob());blobCache.set(name,url);return url;
}
function markdown(element,text){
  // A deliberately small, safe preview subset: line breaks, bold, and inline code.
  // All user content is inserted as text nodes, never HTML.
  const parts=text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  for(const part of parts){if(part.startsWith('**')&&part.endsWith('**'))element.append(node('b','',part.slice(2,-2)));else if(part.startsWith('`')&&part.endsWith('`'))element.append(node('code','',part.slice(1,-1)));else element.append(document.createTextNode(part.replace(/\\([\\*_~`|>\[\]])/g,'$1')));}
}
async function drawEmbed(embed,generation){
  const refs=[embed.image?.url,embed.thumbnail?.url,embed.author?.icon_url,embed.footer?.icon_url];
  const urls=await Promise.all(refs.map(imageUrl));if(generation!==previewGeneration)return;
  const root=$('embed');root.replaceChildren();root.style.borderLeftColor='#'+embed.color.toString(16).padStart(6,'0');
  const img=(url,cls)=>{const e=document.createElement('img');e.src=url;e.className=cls;e.alt='Embed image';e.referrerPolicy='no-referrer';return e;};
  if(urls[1])root.append(img(urls[1],'embed-thumbnail'));
  if(embed.author){const author=node('div','embed-author');if(urls[2])author.append(img(urls[2],''));const name=node(embed.author.url?'a':'span','',embed.author.name);if(embed.author.url){name.href=embed.author.url;name.target='_blank';name.rel='noopener noreferrer';}author.append(name);root.append(author);}
  const title=node(embed.url?'a':'div','embed-title',embed.title);if(embed.url){title.href=embed.url;title.target='_blank';title.rel='noopener noreferrer';}root.append(title);
  if(embed.description){const description=node('div','embed-description');markdown(description,embed.description);root.append(description);}
  const fields=node('div','embed-fields');(embed.fields||[]).forEach(field=>{const box=node('div','embed-field'+(field.inline?' inline':''));const name=node('strong'),value=node('div','value');markdown(name,field.name);markdown(value,field.value);box.append(name,value);fields.append(box);});root.append(fields);
  if(urls[0])root.append(img(urls[0],'embed-image'));
  if(embed.footer||embed.timestamp){const footer=node('div','embed-footer');if(urls[3])footer.append(img(urls[3],''));footer.append(document.createTextNode([embed.footer?.text,embed.timestamp?new Date(embed.timestamp).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}):''].filter(Boolean).join(' · ')));root.append(footer);}
}
async function updatePreview(){
  if(!adminKey)return;const generation=++previewGeneration;
  try{const result=await api('admin/preview',{method:'POST',body:{layout:layout(),sample_count:$('preview-source').value==='sample'?Number($('sample-count').value):null}});if(generation!==previewGeneration)return;await drawEmbed(result.embed,generation);if(generation!==previewGeneration)return;
    $('budget-text').textContent=result.characters.toLocaleString()+' / 6,000 characters';$('budget-bar').value=result.characters;$('shown-text').textContent=`${result.shown} / ${result.total} players shown`;
    $('preview-error').textContent='';$('preview-warnings').replaceChildren(...result.warnings.map(w=>node('p','',w)));if(result.hidden)$('preview-warnings').append(node('p','',result.hidden+' disconnected/paused player(s) hidden by your filter.'));
  }catch(e){if(generation===previewGeneration)$('preview-error').textContent=e.message;}
}
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
