import {useEffect,useRef,useState} from 'react';
import {api,Catalog,Inventory,Prefs} from './types';

const units:Record<string,string>={g:'克',ml:'毫升',piece:'个'};
const noPhotos:File[]=[];
export default function ProposalModal({proposal,photos=noPhotos,catalog,inventory,onClose,onConfirm}:{proposal:any;photos?:File[];catalog:Catalog;inventory:Inventory;onClose:()=>void;onConfirm:(result:{inventory:Inventory;preferences:Prefs})=>void}){
 const isPhoto=proposal.source==='vision'||proposal.image_count>0||photos.length>0;
 const [rows,setRows]=useState<any[]>(proposal.items.map((x:any,i:number)=>({...x,rowKey:i,identity_confirmed:false,action:proposal.kind==='add'?'add':x.action||'set',quantity:isPhoto&&(x.unit==='piece'||catalog.ingredients.find(e=>e.id===x.ingredient_id)?.unit==='piece')?'':x.suggested_quantity??x.quantity??''})));
 const [previews,setPreviews]=useState<string[]>([]);
 const [selectedPhoto,setSelectedPhoto]=useState(0);
 const gallery=useRef<HTMLElement>(null);
 useEffect(()=>{const next=photos.map(file=>URL.createObjectURL(file));setPreviews(next);return()=>next.forEach(url=>URL.revokeObjectURL(url));},[photos]);
 const [prefs,setPrefs]=useState<Prefs|null>(proposal.kind==='intake'?proposal.preferences:null);
 const [resolved,setResolved]=useState(false);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const [receipt,setReceipt]=useState<any>(null);
 const update=(i:number,patch:any)=>setRows(rows.map((x,j)=>i===j?{...x,...patch}:x));
 const duplicate=rows.some((x,i)=>x.ingredient_id&&rows.findIndex(y=>y.ingredient_id===x.ingredient_id)!==i);
 const pendingIdentity=rows.filter(r=>isPhoto&&r.action!=='keep'&&(!r.ingredient_id||!r.identity_confirmed)).length;
 const incomplete=rows.some(r=>!catalog.ingredients.some(x=>x.id===r.ingredient_id)||(r.action!=='keep'&&(r.quantity===''||!Number.isFinite(Number(r.quantity))||Number(r.quantity)<0)));
 const label=(id:string)=>catalog.ingredients.find(i=>i.id===id)?.name||id;
 async function confirm(){
  setError('');setBusy(true);
  try{
   if(receipt){onConfirm(receipt);return;}
   if(duplicate)throw Error('同一食材有多条记录，请核对是否重复，将数量整理到一条并移除其他条目。');
   if(pendingIdentity)throw Error('请逐项核对照片中的食材种类，或保持原库存、移除该项。');
   const changes=rows.map(r=>{const entry=catalog.ingredients.find(i=>i.id===r.ingredient_id);if(!entry)throw Error('请为未知食材选择种类，或移除该项');if(r.action!=='keep'&&(r.quantity===''||!Number.isFinite(Number(r.quantity))))throw Error('请填写实际数量，或选择保持原库存');return {ingredient_id:r.ingredient_id,action:r.action,unit:entry.unit,quantity:r.action==='keep'?null:Number(r.quantity),identity_confirmed:!!r.identity_confirmed};});
   const result=await api('/proposals/'+proposal.id+'/confirm','POST',{inventory_version:proposal.inventory_version,changes,preferences:prefs,questions_resolved:resolved});
   setReceipt(result);onConfirm(result);
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
 }
 return <div className="modal-backdrop"><section className={'modal proposal-modal'+(isPhoto?' has-photos':'')} role="dialog" aria-modal="true" aria-label="核对并确认">
  <div className="section-title"><h2>{proposal.kind==='intake'?'确认 Agent 理解的需求':proposal.kind==='add'?'确认新增食材':'核对冰箱剩余'}</h2><button className="bare" disabled={busy} onClick={onClose}>取消</button></div>
  <div className={isPhoto?'proposal-layout':undefined}>
  {isPhoto&&<aside className="photo-reference" ref={gallery} aria-label="原图对照"><span className="eyebrow">PHOTO REFERENCE</span><h3>对照照片，逐项核对</h3>
   {previews.length>0?<><div className="photo-thumbnails">{previews.map((url,i)=><button key={url} aria-label={'查看照片'+(i+1)} aria-pressed={selectedPhoto===i} onClick={()=>setSelectedPhoto(i)}><img src={url} alt=""/><span>照片 {i+1}</span></button>)}</div><img className="photo-reference-main" src={previews[selectedPhoto]} alt={'原图对照：照片'+(selectedPhoto+1)}/><a className="text-button" href={previews[selectedPhoto]} target="_blank" rel="noreferrer">打开原图放大查看 ↗</a><p className="subtle">对照图只在本次页面中保留；切换和放大不会再次调用识别。</p></>:<p className="subtle">本页没有原图，请对照冰箱实物核对；看不清的食材可保留原库存或移除。</p>}
  </aside>}
  <div className="proposal-content">
  <p className="subtle">{proposal.note}</p><p className="subtle">没拍到的食材保持不变。确认保存不会重复入库；观察结果 30 分钟后过期。</p>
  {error&&<p className="violation" role="alert">{error}</p>}
  {proposal.questions?.length>0&&<div className="proposal-questions"><b>请先核对</b><ul>{proposal.questions.map((q:string,i:number)=><li key={i}>{q}</li>)}</ul></div>}
  {rows.map((row,i)=>{const entry=catalog.ingredients.find(x=>x.id===row.ingredient_id);const stock=inventory.items.find(x=>x.ingredient_id===row.ingredient_id);const uncertain=!row.ingredient_id||['uncertain','unknown'].includes(row.identity_status);return <div className={'observation-card'+(isPhoto&&uncertain?' identity-uncertain':'')} key={row.rowKey}>
   <div className="section-title"><b>{row.name}</b><button className="bare" aria-label={'移除观察'+i} disabled={busy} onClick={()=>setRows(rows.filter((_,j)=>j!==i))}>移除</button></div>
   {row.image_indices?.length>0&&<div className="observation-sources">{row.image_indices.map((n:number)=><button key={n} className="text-button" disabled={!previews[n-1]} onClick={()=>{setSelectedPhoto(n-1);gallery.current?.scrollIntoView({block:'nearest',behavior:'smooth'});}}>对照照片 {n}</button>)}</div>}
   {isPhoto&&<p className={uncertain?'identity-warning':'subtle'}>{row.identity_reason||(uncertain?'种类尚未确认，请手动选择或移除。':'食材名称来自模型建议，请逐项核对。')}{uncertain&&row.suggested_ingredient_id?' 候选：'+label(row.suggested_ingredient_id)+'（未确认）':''}</p>}
   <p className="subtle">{row.basis||row.note}{row.duplicate_group?' · 疑似重复，请合并核对':''}{row.obscured?' · 有遮挡':''}</p>
   {row.note&&row.basis&&row.note!==row.basis&&<p className="subtle">观察说明：{row.note}</p>}
   {row.label_text&&<p className="subtle">读到的标签文字：<q>{row.label_text}</q>（请对照原图核对）</p>}
   <div className="comparison"><span>账面：{stock?stock.quantity+' '+units[stock.unit]:'未登记'}</span><span>观察数量（待核对）：{row.visible_count??'不确定'}{row.visible_count!==undefined&&row.visible_count!==null?' 个':''}</span></div>
   <div className="proposal-fields"><label>食材<select aria-label={'观察食材'+i} value={row.ingredient_id||''} disabled={busy} onChange={e=>update(i,{ingredient_id:e.target.value,quantity:'',identity_confirmed:false})}><option value="">请选择种类</option>{catalog.ingredients.map(x=><option value={x.id} key={x.id}>{x.name}</option>)}</select></label>
   <label>处理方式<select aria-label={'处理方式'+i} value={row.action} disabled={busy} onChange={e=>update(i,{action:e.target.value,identity_confirmed:false})}><option value="set">更新为剩余数量</option><option value="add">新增这份数量</option><option value="keep">保持原库存</option></select></label>
   <label>确认数量（{units[entry?.unit||'g']}）<input aria-label={'确认数量'+i} type="number" min="0" step={entry?.unit==='piece'?1:0.01} disabled={busy||row.action==='keep'} value={row.quantity} onChange={e=>update(i,{quantity:e.target.value})}/></label></div>
   {isPhoto&&row.action!=='keep'&&<label className="check-label identity-check"><input type="checkbox" aria-label={'核对种类'+i} disabled={busy||!entry} checked={row.identity_confirmed} onChange={e=>update(i,{identity_confirmed:e.target.checked})}/>我已对照照片或实物，确认这一项是{entry?'“'+entry.name+'”':'所选食材'}</label>}
  </div>})}
  {duplicate&&<p className="violation">发现同类食材多条记录：确认是否为独立包装，将总剩余量填入一条并移除其他条目。系统不会自动相加。</p>}
  {prefs&&<div className="confirmed-preferences"><h3>这次用餐要求</h3><div className="proposal-fields"><label>人数<select aria-label="确认用餐人数" value={prefs.diners} onChange={e=>setPrefs({...prefs,diners:+e.target.value})}>{[1,2,3,4,5].map(n=><option key={n} value={n}>{n} 人</option>)}</select></label><label>顿数<select value={prefs.meals} onChange={e=>setPrefs({...prefs,meals:+e.target.value})}>{[1,2].map(n=><option key={n} value={n}>{n} 顿</option>)}</select></label><label>每顿分钟<input type="number" min="5" max="120" value={prefs.minutes_per_meal} onChange={e=>setPrefs({...prefs,minutes_per_meal:+e.target.value})}/></label></div><p>厨具：{prefs.equipment.map(x=>catalog.equipment[x]).join('、')||'未选择'}；优先：{prefs.priority_ingredients.map(label).join('、')||'无'}</p><p>忌口：{[...prefs.excluded_ingredients.map(label),...prefs.excluded_allergens.map(x=>catalog.allergens[x])].join('、')||'无'}；口味：{prefs.taste}</p><p className="subtle">未修改的条件继续保留；其他条件可在确认后通过主表单调整。{prefs.allow_draft_recipes?'本次允许待审核示例。':'只使用已审核配方。'}</p></div>}
  {proposal.questions?.length>0&&<label className="check-label"><input type="checkbox" checked={resolved} onChange={e=>setResolved(e.target.checked)}/>我已补充或移除不确定项，并处理以上问题</label>}
  {pendingIdentity>0&&<p className="identity-warning" role="status">还有 {pendingIdentity} 项食材种类待核对；看不清时可以保留原库存或移除。</p>}
  {incomplete&&<p className="subtle">请补齐保留条目的种类和实际数量。</p>}
  <button className="button full" disabled={busy||duplicate||incomplete||pendingIdentity>0||(proposal.questions?.length>0&&!resolved)} onClick={confirm}>{busy?'正在保存…':'确认并保存'}</button>
  </div></div>
 </section></div>
}
