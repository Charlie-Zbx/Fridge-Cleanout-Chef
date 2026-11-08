export type Item = {ingredient_id:string;quantity:number|string;unit:string};
export type Inventory = {items:Item[];pantry:string[];version:number};
export type Prefs = {diners:number;meals:number;minutes_per_meal:number;equipment:string[];excluded_ingredients:string[];excluded_allergens:string[];priority_ingredients:string[];taste:string;allow_draft_recipes:boolean};
export type Ingredient = {id:string;name:string;unit:string;allergens:string[];aliases:string[]};
export type Recipe = {id:string;name:string;ingredients:Item[];pantry:string[];equipment:string[];minutes:number;steps:string[];source_label:string;reviewed:boolean;reviewed_at:string|null;cooked_count:number;team_reviewed:boolean;serving_profiles:Record<string,{minutes:number;batches:number;instructions:string}>;servings?:number;batches?:number;batch_instructions?:string};
export type Catalog = {ingredients:Ingredient[];pantry:Record<string,string>;equipment:Record<string,string>;allergens:Record<string,string>;recipes:Recipe[]};
export type Trace = {kind:string;event_id?:string;source_event_id?:string;tool?:string;tools?:string[];arguments?:unknown;result?:any;ok?:boolean;error?:string;duration_ms?:number;round?:number;message?:string};
export type Run = {id:string;revision:number;created_at:string;status:string;message:string;mode:string;plan:any;preferences:Prefs;trace:Trace[];confirmed_meals:number[];model_calls:number;usage:Record<string,number>;duration_ms:number;validation?:{feasible:boolean;remaining:Item[];uses_draft_recipes:boolean;meals:{index:number;minutes:number;consumption:Record<string,number>;dishes:(Recipe & {servings:number;quantities:(Item&{name:string})[]})[]}[]}};
export async function api(path:string,method='GET',data?:unknown){
 const response=await fetch('/api'+path,{method,credentials:'same-origin',headers:{'X-Kitchen-Client':'fridge-web',...(data instanceof FormData?{}:{'Content-Type':'application/json'})},body:data===undefined?undefined:data instanceof FormData?data:JSON.stringify(data)});
 const body=await response.json();
 if(!response.ok) throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail));
 return body;
}
