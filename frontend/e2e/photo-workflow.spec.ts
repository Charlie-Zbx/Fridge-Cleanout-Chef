import {test,expect,Page} from '@playwright/test';
import fs from 'node:fs';

// Synthetic 1px PNG. No dependency on downloaded photos and no model uploads.
const photo={name:'fixture.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a0XcAAAAASUVORK5CYII=','base64')};

async function mockPhoto(page:Page){
 let calls=0;
 await page.route('**/api/session',async route=>{
  const response=await route.fetch();
  await route.fulfill({response,json:{...await response.json(),live_enabled:true}});
 });
 await page.route('**/api/vision',async route=>{
  calls++;
  const response=await page.request.post('/api/stocktakes',{headers:{'x-kitchen-client':'fridge-web'}});
  const proposal=await response.json();
  await route.fulfill({json:{...proposal,source:'vision',image_count:2,note:'模拟照片，仅测试流程；数量来自测试用例。',items:[
   {name:'鸡蛋',ingredient_id:'egg',visible_count:3,suggested_quantity:3,image_indices:[1],identity_status:'clear'},
   {name:'种类不确定的蔬菜',ingredient_id:null,suggested_ingredient_id:'bok_choy',suggested_quantity:null,image_indices:[1,2],identity_status:'uncertain',identity_reason:'种类不确定，已清空预选；请对照照片选择。'}
  ]}});
 });
 await page.goto('/');
 await page.getByRole('button',{name:'用三种食材体验一下'}).click();
 await page.getByRole('checkbox',{name:/确认本次付费 API 调用/}).check();
 await page.locator('.photo-actions label').filter({hasText:'拍照核对剩余'}).locator('input').setInputFiles([photo,photo]);
 await expect(page.getByRole('dialog',{name:'核对并确认'})).toBeVisible();
 return()=>calls;
}

test('photo to plan to revised plan to consumption: offline full journey',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 const calls=await mockPhoto(page);
 await expect(page.getByAltText('原图对照：照片1')).toBeVisible();
 await page.getByRole('button',{name:'查看照片2',exact:true}).click();
 await expect(page.getByAltText('原图对照：照片2')).toBeVisible();
 expect(calls()).toBe(1);
 await expect(page.getByLabel('观察食材1',{exact:true})).toHaveValue('');
 await expect(page.getByLabel('确认数量0',{exact:true})).toHaveValue('');
 await page.getByLabel('确认数量0',{exact:true}).fill('3');
 await expect(page.getByRole('button',{name:'确认并保存',exact:true})).toBeDisabled();
 await page.getByLabel('观察食材1',{exact:true}).selectOption('cabbage');
 await page.getByLabel('确认数量1',{exact:true}).fill('200');
 await page.getByLabel('核对种类0',{exact:true}).check();
 await page.getByLabel('核对种类1',{exact:true}).check();
 await page.getByLabel('观察食材1',{exact:true}).selectOption('bok_choy');
 await expect(page.getByLabel('核对种类1',{exact:true})).not.toBeChecked();
 await expect(page.getByLabel('确认数量1',{exact:true})).toHaveValue('');
 await page.getByLabel('观察食材1',{exact:true}).selectOption('cabbage');
 await page.getByLabel('确认数量1',{exact:true}).fill('200');
 await page.getByLabel('核对种类1',{exact:true}).check();
 const before=await (await page.request.get('/api/inventory')).json();
 expect(before.items.find((x:any)=>x.ingredient_id==='cabbage').quantity).toBe('200');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 fs.mkdirSync('../artifacts',{recursive:true});
 await page.screenshot({path:'../artifacts/mobile-photo-identity.png',fullPage:true});
 await page.getByRole('button',{name:'确认并保存',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'核对并确认'})).not.toBeVisible();
 await expect(page.getByLabel('豆腐库存')).toHaveValue('300');
 await page.getByRole('button',{name:'安排我的饭菜'}).click();
 await expect(page.getByText('计划完成后，预计还剩')).toBeVisible({timeout:60000});
 await page.getByRole('button',{name:'修改条件',exact:true}).click();
 await page.getByRole('button',{name:'30 分钟',exact:true}).click();
 await page.getByRole('button',{name:'更新这份计划',exact:true}).click();
 await expect(page.getByText('离线模拟 · 第 2 版',{exact:true})).toBeVisible({timeout:60000});
 await expect(page.getByText('计划完成后，预计还剩')).toBeVisible({timeout:60000});
 const run=(await (await page.request.get('/api/runs')).json())[0];
 expect(run.status).toBe('ready');
 expect(run.validation.feasible).toBe(true);
 expect(run.trace.some((t:any)=>t.kind==='mcp_tool'&&t.tool.endsWith('evaluate_plan'))).toBeTruthy();
 await page.getByRole('button',{name:'做完了，确认实际用量'}).first().click();
 await page.getByRole('button',{name:'确认做完并更新库存'}).click();
 await page.getByRole('button',{name:'稍后再说'}).click();
 await expect(page.getByRole('button',{name:'这一顿已确认'})).toBeDisabled();
 const after=await (await page.request.get('/api/inventory')).json();
 const consumption=run.validation.meals[0].consumption;
 for(const item of after.items){
  const old=before.items.find((x:any)=>x.ingredient_id===item.ingredient_id);
  expect(Number(item.quantity)).toBe(Number(old.quantity)-Number(consumption[item.ingredient_id]||0));
 }
 const repeated=await page.request.post('/api/runs/'+run.id+'/confirm',{headers:{'x-kitchen-client':'fridge-web'},data:{meal_index:0,revision:run.revision,inventory_version:after.version,actual:consumption}});
 expect(repeated.ok()).toBeTruthy();
 expect((await repeated.json()).already_confirmed).toBe(true);
 expect(await (await page.request.get('/api/inventory')).json()).toEqual(after);
 await page.reload();
 await expect(page.getByLabel('卷心菜库存')).toHaveValue('50');
 expect(calls()).toBe(1);
});

test('cancel photo confirmation releases previews and does not change stock',async({page})=>{
 await page.addInitScript(()=>{
  const original=URL.revokeObjectURL;
  (window as any).releasedPhotos=[];
  URL.revokeObjectURL=(url:string)=>{(window as any).releasedPhotos.push(url);original(url);};
 });
 const calls=await mockPhoto(page);
 const before=await (await page.request.get('/api/inventory')).json();
 const url=await page.getByAltText('原图对照：照片1').getAttribute('src');
 await page.screenshot({path:'../artifacts/desktop-photo-identity.png',fullPage:true});
 await page.getByRole('button',{name:'取消',exact:true}).click();
 expect(await (await page.request.get('/api/inventory')).json()).toEqual(before);
 expect(await page.evaluate(()=> (window as any).releasedPhotos)).toContain(url);
 await page.getByRole('button',{name:'手动核对剩余'}).click();
 await expect(page.getByRole('complementary',{name:'原图对照'})).not.toBeVisible();
 expect(calls()).toBe(1);
});
