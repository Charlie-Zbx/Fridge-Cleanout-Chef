import {test,expect} from '@playwright/test';
import fs from 'node:fs';

test('verified no-plan shows reason and a real single search in the trace',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto('/');
 await page.getByRole('button',{name:'用三种食材体验一下'}).click();
 await expect(page.getByLabel('鸡蛋库存')).toHaveValue('3');
 await page.getByLabel('用餐人数',{exact:true}).selectOption('5');
 await page.getByRole('button',{name:'安排我的饭菜'}).click();
 await expect(page.getByText(/已检查当前库的30道配方/)).toBeVisible({timeout:60000});
 await page.getByRole('button',{name:'查看这次的工具调用与检查记录'}).click();
 await expect(page.getByText('全库检查：当前无可行菜品',{exact:true})).toBeVisible();
 const run=(await (await page.request.get('/api/runs')).json())[0];
 expect(run.status).toBe('no_plan');
 expect(run.model_calls).toBe(1);
 expect(run.trace.filter((e:any)=>e.kind==='mcp_tool')).toHaveLength(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
 await page.screenshot({path:'../artifacts/mobile-no-plan-reason.png',fullPage:true});
});

test('mobile photo confirmation: unknown quantity, duplicate and unseen inventory (mock vision)',async({page})=>{
 const photo='../evaluation/photos/web_sources/gfp-fridge-contents.jpg';
 test.skip(!fs.existsSync(photo),'Optional public-source fixture has not been downloaded');
 await page.setViewportSize({width:390,height:844});
 await page.route('**/api/session',async route=>{
  const response=await route.fetch();
  await route.fulfill({response,json:{...await response.json(),live_enabled:true}});
 });
 let intercepted=0;
 await page.route('**/api/vision',async route=>{
  intercepted++;
  // Entire vision request is intercepted. A real local stocktake proposal tests confirmation.
  const created=await page.request.post('/api/stocktakes',{headers:{'x-kitchen-client':'fridge-web'}});
  expect(created.ok()).toBeTruthy();
  const proposal=await created.json();
  await route.fulfill({json:{...proposal,note:'模拟视觉结果，仅测试确认流程。',items:[
   {name:'牛奶',ingredient_id:'milk',visible_count:1,suggested_quantity:null,image_indices:[1],label_text:'测试夹具标签：1000 ml',note:'已开封，剩余量不清楚',basis:'需要人工填写',duplicate_group:'milk-A'},
   {name:'疑似同一瓶牛奶',ingredient_id:'milk',visible_count:1,suggested_quantity:null,image_indices:[2],duplicate_group:'milk-A'},
   {name:'锡纸覆盖容器',ingredient_id:null,suggested_quantity:null,image_indices:[1],obscured:true,note:'看不到内容，不能猜内部食材'}
  ]}});
 });
 await page.goto('/');
 await page.getByRole('button',{name:'用三种食材体验一下'}).click();
 await expect(page.getByLabel('鸡蛋库存')).toHaveValue('3');
 await page.getByRole('checkbox',{name:/确认本次付费 API 调用/}).check();
 await page.locator('.photo-actions label').filter({hasText:'拍照核对剩余'}).locator('input').setInputFiles([photo,photo]);
 await expect(page.getByRole('dialog',{name:'核对并确认'})).toBeVisible();
 await expect(page.getByLabel('确认数量0',{exact:true})).toHaveValue('');
 await expect(page.getByText('观察说明：已开封，剩余量不清楚')).toBeVisible();
 await expect(page.getByText(/读到的标签文字/)).toBeVisible();
 await expect(page.getByRole('button',{name:'确认并保存',exact:true})).toBeDisabled();
 const before=await (await page.request.get('/api/inventory')).json();
 expect(before.items.some((x:any)=>x.ingredient_id==='milk')).toBeFalsy();
 await page.getByLabel('移除观察2',{exact:true}).click();
 await page.getByLabel('移除观察1',{exact:true}).click();
 await page.getByLabel('确认数量0',{exact:true}).fill('250'); // Explicit fixture confirmation, not a photo ground truth.
 await page.getByLabel('核对种类0',{exact:true}).check();
 await page.screenshot({path:'../artifacts/mobile-photo-confirmation.png',fullPage:true});
 await page.getByRole('button',{name:'确认并保存',exact:true}).click();
 await expect(page.getByLabel('牛奶库存')).toHaveValue('250');
 await expect(page.getByLabel('鸡蛋库存')).toHaveValue('3');
 await expect(page.getByLabel('卷心菜库存')).toHaveValue('200');
 expect(intercepted).toBe(1);
});

test('desktop: real MCP repair, inventory confirmation and persistence',async({page})=>{
 const errors:string[]=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');
 await expect(page.getByText('先放进第一种食材')).toBeVisible();
 await expect(page.getByRole('option',{name:'DeepSeek Agent（尚未启用）'})).toBeDisabled();
 fs.mkdirSync('../artifacts',{recursive:true});
 await page.screenshot({path:'../artifacts/desktop-empty.png',fullPage:true});
 await page.getByRole('button',{name:'用三种食材体验一下'}).click();
 await expect(page.getByLabel('鸡蛋库存')).toHaveValue('3');
 await page.getByRole('button',{name:'安排我的饭菜'}).click();
 await expect(page.getByRole('heading',{name:'下一顿，有着落。'})).toBeVisible({timeout:60000});
 await expect(page.getByText('计划完成后，预计还剩')).toBeVisible({timeout:60000});
 await page.screenshot({path:'../artifacts/desktop-plan.png',fullPage:true});
 await page.getByRole('button',{name:'查看这次的工具调用与检查记录'}).click();
 await expect(page.getByText('发现约束冲突',{exact:true})).toBeVisible();
 await expect(page.getByText('方案通过检查',{exact:true})).toBeVisible();
 await page.screenshot({path:'../artifacts/desktop-trace.png',fullPage:true});
 await page.getByRole('button',{name:'用餐计划',exact:true}).click();
 await page.getByRole('button',{name:'修改条件',exact:true}).click();
 await page.getByRole('button',{name:'30 分钟',exact:true}).click();
 await page.getByRole('button',{name:'更新这份计划',exact:true}).click();
 await expect(page.getByText('离线模拟 · 第 2 版',{exact:true})).toBeVisible({timeout:60000});
 const history=await page.request.get('/api/runs');
 expect((await history.json()).length).toBe(1);
 await page.getByRole('button',{name:'做完了，确认实际用量'}).first().click();
 await page.getByRole('button',{name:'确认做完并更新库存'}).click();
 await expect(page.getByRole('heading',{name:'这一顿吃得怎么样？'})).toBeVisible();
 await page.getByRole('button',{name:'稍后再说'}).click();
 await expect(page.getByRole('button',{name:'这一顿已确认'})).toBeDisabled();
 await page.getByRole('button',{name:'我的冰箱',exact:false}).click();
 await expect(page.getByLabel('卷心菜库存')).toHaveValue('50');
 await page.reload();
 await expect(page.getByLabel('卷心菜库存')).toHaveValue('50');
 expect(errors).toEqual([]);
});

test('mobile: five people intake confirmation and stocktake replaces rather than adds',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto('/');
 await page.getByRole('button',{name:'用三种食材体验一下'}).click();
 await page.getByLabel('补充想法').fill('改成五个人吃，每顿45分钟');
 await page.getByRole('button',{name:'整理这句话，先让我确认'}).click();
 await expect(page.getByRole('dialog',{name:'核对并确认'})).toBeVisible();
 await expect(page.getByLabel('确认用餐人数')).toHaveValue('5');
 const before=await (await page.request.get('/api/inventory')).json();
 expect(before.items.find((x:any)=>x.ingredient_id==='egg').quantity).toBe('3');
 await page.screenshot({path:'../artifacts/mobile-intake-confirmation.png',fullPage:true});
 await page.getByRole('button',{name:'确认并保存',exact:true}).click();
 await expect(page.getByLabel('用餐人数',{exact:true})).toHaveValue('5');
 await page.getByRole('button',{name:'手动核对剩余'}).click();
 await expect(page.getByRole('heading',{name:'核对冰箱剩余'})).toBeVisible();
 await page.getByLabel('确认数量0',{exact:true}).fill('1');
 await page.getByLabel('处理方式1',{exact:true}).selectOption('keep');
 await page.getByLabel('处理方式2',{exact:true}).selectOption('keep');
 await page.screenshot({path:'../artifacts/mobile-stocktake.png',fullPage:true});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
 await page.getByRole('button',{name:'确认并保存',exact:true}).click();
 await expect(page.getByLabel('鸡蛋库存')).toHaveValue('1');
 await expect(page.getByLabel('卷心菜库存')).toHaveValue('200');
 await page.reload();
 await expect(page.getByLabel('用餐人数',{exact:true})).toHaveValue('5');
 await expect(page.getByLabel('鸡蛋库存')).toHaveValue('1');
});

test('five-person planning displays batch time and live progress',async({page})=>{
 await page.goto('/');
 await page.getByRole('button',{name:'用三种食材体验一下'}).click();
 await page.getByLabel('用餐人数',{exact:true}).selectOption('5');
 await page.getByLabel('鸡蛋库存').fill('20');
 await page.getByLabel('卷心菜库存').fill('1000');
 await page.getByLabel('豆腐库存').fill('1500');
 await page.getByRole('button',{name:'60 分钟',exact:true}).click();
 await page.getByRole('button',{name:'安排我的饭菜'}).click();
 await expect(page.getByRole('heading',{name:'Agent 正在规划'})).toBeVisible();
 await expect(page.getByText('计划完成后，预计还剩')).toBeVisible({timeout:60000});
 await expect(page.locator('.batch-note').first()).toContainText('5 人份 · 3 批');
 await page.screenshot({path:'../artifacts/five-person-plan.png',fullPage:true});
 const history=await (await page.request.get('/api/runs')).json();
 expect(history[0].validation.feasible).toBeTruthy();
 expect(history[0].validation.meals.every((m:any)=>m.minutes<=60)).toBeTruthy();
});

test('mobile: layout, editable inventory and recipe review',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto('/');
 await expect(page.getByText('先放进第一种食材')).toBeVisible();
 await page.getByLabel('选择食材').selectOption('egg');
 await page.getByLabel('新增数量').fill('5');
 await page.getByRole('button',{name:'添加食材',exact:true}).click();
 await page.getByRole('button',{name:'保存库存',exact:true}).click();
 await expect(page.getByLabel('鸡蛋库存')).toHaveValue('5');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
 await page.screenshot({path:'../artifacts/mobile-fridge.png',fullPage:true});
 await page.getByRole('button',{name:'菜谱小册',exact:true}).click();
 await page.getByLabel('搜索菜谱').fill('香煎豆腐');
 await page.getByRole('button').filter({has:page.getByRole('heading',{name:'香煎豆腐'})}).click();
 await page.getByRole('button',{name:'我已检查以上配方，标记为已审核'}).click();
 await expect(page.getByText('30 道开发示例 · 1 道已审核')).toBeVisible();
 await page.screenshot({path:'../artifacts/mobile-recipes.png',fullPage:true});
});
