# 检索复用、无解说明与新照片批次

2026-11-08。本轮按用户要求优化Agent并寻找不同照片。16次上限批次实际8次后因图片结构校验失败终止；Agent验证通过，格式兼容已离线修复。之后另获2次图片补测授权并完成2次。本轮合计10次请求，全部已结束，照片仍有数量/类别错误。结果见LIVE_EFFICIENCY_TEST.md。下文保留实施和原计划。

## 实现与边界

- `search_recipes`扫描当前确认快照的整个菜谱库，返回全库可行单菜数、受阻原因计数和至多两个未通过例子。关键词只改变排序，分页不影响全库诊断。
- 同一次运行内，相同工具参数的成功结果复用，包含并发重复请求。失败结果不缓存，用户/任务/新条件之间不共享缓存。轨迹区分真实`mcp_tool`与`tool_cache`，缓存事件引用真实来源事件。
- 只有真实MCP返回“全库无可行单菜”，且宿主用确认快照再次验证后，才在下一轮模型请求之前终止。说明由程序根据检查原因构造，明确受限制的配方不是可用候选。
- 某页为空、某个菜品组合失败、一个单菜可行但两顿库存不足，都不能触发上述终止。仍保留正常组合校验及重规划。
- 这是工具诊断与执行控制优化；不能将减少的模型调用归功于模型本身推理能力提升。它仅对当前固定库和明确的份数/时间/库存规则成立，不证明现实中不存在其他做法。

后端全量82项通过，另新增1项未授权批次测试通过；前端构建通过，6项浏览器流程通过，冻结20场景离线回归20/20通过。新的无解场景离线与真实DeepSeek各验证一次，均为1轮决策＋1次真实stdio MCP检索；真实结果详见LIVE_EFFICIENCY_TEST.md。

## 三张新照片

1. `veg_bin`：蔬菜抽屉近景，西兰花、茄子、西葫芦、番茄，含遮挡。来源：[Alabama Extension / Margaret Barse](https://www.flickr.com/photos/184594136@N08/50838442242/)，[CC0许可记录](https://commons.wikimedia.org/wiki/File:Vegetables_in_Refrigerator_Bin_-_50838442242.jpg)。
2. `veg_fridge`：同组冰箱较宽视角，蔬菜、包装、瓶罐和未展开的蛋盒。来源：[Alabama Extension / Margaret Barse](https://www.flickr.com/photos/184594136@N08/50837632593/)，[CC0许可记录](https://commons.wikimedia.org/wiki/File:Fruits_and_Vegetables_in_Refrigerator.jpg)。
3. `egg_container`：半透明容器里的重叠鸡蛋，玻璃反射，旁边包装显示营养表的15mL每份用量。来源：[USDA / Lance Cheung](https://www.flickr.com/photos/41284017@N08/49990592782/)，[公共领域记录](https://commons.wikimedia.org/wiki/File:Food_Safety_-_Cut_Waste_in_Refrigerators_(20200608-FSIS-LSC-0211).jpg)。

下载的是发布者提供的约1024像素JPEG预览，没有本地裁剪或修改。原文件哈希和许可记录见evaluation/web-photo-manifest.json；调用前的本地观察记录见evaluation/diverse-photo-observations.json。没有实物称重真值。

前两张同一拍摄组且内容重叠，不计作两个独立冰箱样本；双图测试检查是否避免将同一食物跨图累加。第三张来自不同拍摄来源。Wikimedia原图下载返回429后未继续重试，改用各摄影者Flickr页面直接提供的公开预览。

## 待批准的真实批次

冻结定义：evaluation/efficiency-batch.json；脚本：scripts/verify_efficiency.py。无参数只做本地预检，不联网。

| 测试 | 请求上限 |
|---|---:|
| 五人、每顿20分钟的同一无解场景；对照旧记录的5轮模型/3次检索 | 6 |
| 五人、每顿90分钟的可行对照，确认优化没有误拒绝可行任务 | 6 |
| 三张新照片分别识别 | 3 |
| 两张蔬菜视角一起识别，检查重复物品处理 | 1 |
| 合计 | **16** |

仅上传上述3张新图；双图组复用其中2张，不上传旧gfp01。每次最多3000输出token；每次Agent最多90秒、6次模型请求和12次工具请求；每批照片最多1次请求、40秒；整批最多7分钟。无自动重试，接口/结构/关键程序检查失败则停止整批，不自动纠正后追加请求。

独立测试数据与检查点留在项目artifacts下，不使用实际厨房、不扣库存。模型结果与token原样记录，图片质量完成后单独比对，不把结构通过当作识别准确。批准前不能使用`--approve-max-calls 16`；本文件本身不是授权。
