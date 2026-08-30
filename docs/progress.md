# Product Picker Development Progress

## Phase 0

状态：  
Completed

内容：

- 项目初始化完成

## Phase 1

状态：  
Completed

内容：

- Product 模型
- SQLite 数据库
- 数据库测试

## Phase 2.1

状态：  
Completed

内容：

- BaseScraper 接口

## Phase 2.2

状态：  
Completed

内容：

- Reddit RSS scraper

## Phase 3

状态：  
Completed

完成日期：2026-08-20

修改文件：

- `main.py`
- `db.py`
- `tests/test_pipeline.py`
- `docs/progress.md`

新增能力：

- Reddit Product 批量保存至 SQLite
- 基于 URL 的重复数据跳过与计数
- 查询数据库全部 Product 数据
- 可观察的最小 Pipeline 运行日志
- Reddit 不可访问时的错误报告与安全退出

测试结果：

- `pytest`：9 passed

下一阶段建议：

- 审核 Phase 3 的真实运行数据与日志后，再确定下一阶段范围

## Phase 4

状态：  
Completed

完成日期：2026-08-20

修改文件：

- `scrapers/reddit.py`
- `rule_filter.py`
- `db.py`
- `main.py`
- `tests/test_reddit.py`
- `tests/test_pipeline.py`
- `tests/test_rule_filter.py`
- `docs/progress.md`

新增能力：

- Reddit 请求 User-Agent、超时、重试及明确错误信息
- 免费确定性 Rule Filter 规则层
- SQLite 过滤结果字段与旧数据库自动迁移
- Pipeline 候选与拒绝数量统计

测试结果：

- `pytest`：13 passed

下一阶段建议：

- 审核 Phase 4 的规则分数与真实运行日志后，再确定下一阶段范围

## Phase 5.1

状态：  
Completed

完成日期：2026-08-20

修改文件：

- `scrapers/product_hunt.py`
- `tests/test_product_hunt.py`
- `docs/progress.md`

新增能力：

- Product Hunt 公开 RSS scraper
- Product Hunt 条目到统一 Product 模型的字段映射
- 网络、页面解析、空数据及单条无效数据处理
- mock RSS 测试，不依赖真实 Product Hunt 网络

测试结果：

- `pytest`：16 passed

当前能力变化：

- 项目目前具备 Reddit 与 Product Hunt 两个数据源适配器

下一阶段建议：

- 审核 Product Hunt 字段映射后，再确定下一阶段范围

## Phase 5.2

状态：  
Completed

完成日期：2026-08-20

修改文件：

- `main.py`
- `tests/test_pipeline.py`
- `docs/progress.md`

新增能力：

- Reddit 与 Product Hunt 多源 Pipeline
- scraper 列表依次执行与统一 Product 汇总
- 单个数据源失败时继续处理其他数据源
- 多源数据统一经过 Rule Filter 并保存至 SQLite

测试结果：

- `pytest`：18 passed

下一阶段建议：

- 审核多源 Pipeline 的真实运行日志后，再确定下一阶段范围

## Phase 5.3

状态：  
Completed

完成日期：2026-08-22

修改文件：

- `rule_filter.py`
- `db.py`
- `main.py`
- `tests/test_rule_filter.py`
- `tests/test_pipeline.py`
- `docs/progress.md`

产品机会结构：

- Physical Product Opportunities 为主赛道
- Software Opportunities 为副赛道
- Inspiration 作为未来设计灵感池
- 无法可靠分类的产品进入 Uncertain

新增能力：

- 免费规则对 physical、software、inspiration、uncertain 分类
- 实体商品与软件机会使用独立评分规则
- SQLite 兼容迁移并保存 `opportunity_type`
- Pipeline 输出机会类型及各赛道候选数量

Product Hunt 真实数据重新分类：

- 总数：50
- Physical：0
- Software：12
- Inspiration：0
- Uncertain：38
- Physical Candidates：0
- Software Candidates：12
- Rejected：0
- Uncertain status：38

测试结果：

- `pytest`：25 passed

下一阶段建议：

- 人工审核双赛道分类结果后，再确定下一阶段范围

## Phase 5.4

状态：  
Completed

完成日期：2026-08-22

修改文件：

- `scrapers/product_hunt.py`
- `rule_filter.py`
- `tests/test_product_hunt.py`
- `tests/test_rule_filter.py`
- `docs/progress.md`

数据增强策略：

- 保留公开 RSS 作为产品列表来源并清理 tagline
- 使用公开产品页的 JSON-LD、OpenGraph、meta 与 canonical 信息补充上下文
- topics、tagline、website、maker/platform 和结构化 metadata 保存在 `raw_data`
- Rule Filter 优先读取 topics、category、tagline 与 metadata，仅以少量高置信度关键词辅助分类，避免继续单纯堆叠标题关键词

真实获取结果：

- Fetched：50
- With topics/category：0
- With richer metadata：0
- 产品公开页面返回 HTTP 403 Forbidden，未伪造增强信息
- 旧历史记录未删除；31 条已有 URL 更新，19 条当前新记录追加保存

当前批次重新分类：

- Physical：1
- Software：12
- Inspiration：0
- Uncertain：37
- Phase 5.3 Uncertain：38
- Phase 5.4 Uncertain：37

测试结果：

- `pytest`：31 passed

下一阶段建议：

- 审核 Phase 5.4 数据增强限制和当前批次分类结果后，再确定下一阶段范围

## Phase 6.1

状态：  
Completed

完成日期：2026-08-22

修改文件：

- `scrapers/kickstarter.py`
- `tests/test_kickstarter.py`
- `docs/progress.md`

数据获取方式：

- 使用 Kickstarter 官方公开 Discover 分类页面
- 优先解析公开 JSON-LD，兼容页面公开的 `data-project` / `data-projects` 结构化属性
- 不登录、不绕过访问限制、不使用私有接口

市场验证字段：

- 支持 goal、pledged、currency、backers、campaign status、deadline、creator、location
- goal 大于 0 且 pledged 可用时计算 funding percentage
- 缺失字段保持 `null`，不编造数据

真实访问结果：

- Kickstarter unavailable
- Fetched：0
- 官方 Discover 页面返回 HTTP 403 Forbidden
- 未写入数据库，未伪造真实项目或市场验证字段

测试结果：

- `pytest`：35 passed

下一阶段建议：

- 审核 Kickstarter 的公开访问限制后，再确定下一阶段范围

## Data Access Foundation

状态：  
Completed

完成日期：2026-08-25

修改文件：

- `.env.example`
- `config.py`
- `scrapers/kickstarter.py`
- `scrapers/arctic_shift.py`
- `tests/test_kickstarter.py`
- `tests/test_arctic_shift.py`
- `docs/progress.md`

Etsy：

- API key、shared secret、access token、refresh token 配置占位已准备
- 本地 `.env` 已创建并由 `.gitignore` 忽略
- 配置读取与 `is_etsy_configured()` 状态检查已完成
- 未写入或记录真实 API 凭证

Kickstarter：

- 直接访问 Kickstarter 的 HTTP 403 路径已冻结，不再作为主路径
- KickstarterScraper 已切换为 KSInsights 公开 CSV adapter
- 通过 GitHub 公共目录索引定位最新 daily CSV，不 clone 第三方仓库
- KSInsights 真实只读探测：available，Fetched 555

Reddit：

- 现有 Reddit RSS scraper 保留，作为实时通道
- 新增 Arctic Shift 第三方历史数据 adapter；非 Reddit 官方 API，不保证实时性或 uptime
- Arctic Shift 真实只读探测：available，r/EDC Fetched 5

测试结果：

- `pytest`：38 passed

下一阶段建议：

- 审核 Data Access Foundation 后，再决定是否进入 Etsy scraper 开发

## Phase 6.2

状态：  
Completed

完成日期：2026-08-25

修改文件：

- `main.py`
- `rule_filter.py`
- `tests/test_pipeline.py`
- `tests/test_rule_filter.py`
- `docs/progress.md`

新增能力：

- KSInsights 正式接入主 Pipeline，显示为 Kickstarter / KSInsights
- Arctic Shift 正式接入主 Pipeline，显示为 Reddit / Arctic Shift
- 单个 scraper 失败时继续执行其他来源
- 每来源默认处理上限：Product Hunt 50、KSInsights 100、Arctic Shift 50
- Kickstarter `percent_funded >= 100` 增加基础市场验证 reason
- Kickstarter `percent_funded >= 300` 增加强筹款验证 reason
- Arctic Shift 历史互动字段进入可解释过滤上下文，不改变主分类逻辑

真实运行汇总：

- Product Hunt：Fetched 50，Processed 50
- KSInsights：Fetched 555，Processed 100
- Arctic Shift：本次读取超时，Fetched 0，Processed 0
- Physical：13
- Software：21
- Inspiration：0
- Uncertain：116
- Kickstarter funded >=100%：97
- Kickstarter funded >=300%：92
- Saved：142
- Duplicates：8

测试结果：

- `pytest`：42 passed

下一阶段建议：

- 审核 Phase 6.2 多源运行结果后，再确定下一阶段范围

## Phase 6.3

状态：  
Completed

完成日期：2026-08-25

修改文件：

- `feasibility_filter.py`
- `db.py`
- `main.py`
- `rule_filter.py`
- `tests/test_feasibility_filter.py`
- `tests/test_pipeline.py`
- `tests/test_rule_filter.py`
- `docs/progress.md`

个人卖家可执行性预筛选：

- Physical 只表示实体商品机会类型，不等于个人卖家可执行
- 新增独立 Feasibility Filter，输出 PASS、REVIEW、REJECT、0–100 分数、原因与风险标记
- 数据库通过最小迁移保存 feasibility 字段，未删除或重建旧数据库
- 筹款比例与支持者数量不参与可执行性判定
- 保留 Kickstarter funded >=100% 市场验证信号，停止使用 >=300% strong crowdfunding validation

真实运行汇总：

- Product Hunt：Fetched 50，Processed 50
- Kickstarter / KSInsights：Fetched 555，Processed 100
- Reddit / Arctic Shift：Fetched 49，Processed 49
- Physical：21，Software：23，Inspiration：0，Uncertain：155
- Feasibility PASS：0，REVIEW：155，REJECT：44
- Feasible Physical Candidates：0
- 主要拒绝风险：complex_electronics 29、weapon_or_blade 12、wireless 7、high_regulation 4
- Saved：48，Duplicates：151

测试结果：

- `pytest`：53 passed

## Phase 6.4 - Source-aware Opportunity Routing

状态：  
Completed

完成日期：2026-08-25

修改文件：

- `demand_signal_filter.py`
- `feasibility_filter.py`
- `db.py`
- `main.py`
- `tests/test_demand_signal_filter.py`
- `tests/test_feasibility_filter.py`
- `tests/test_pipeline.py`
- `docs/progress.md`

按来源分流：

- 新增 `record_role`，区分 product、demand_signal、software、inspiration 和 uncertain
- Reddit 中的寻找、推荐、价格痛点、功能缺口与 DIY 帖子描述的是用户需求，不是已存在的商品方案，因此不再进入普通 Product Feasibility Filter
- demand_signal 进入独立需求信号评分，商品记录才执行 feasibility 判定
- 增强 dock、SSD、charging hub、battery hub、Thunderbolt 和高速存储等复杂电子风险识别
- 区分物理收纳与数字存储，不将 SSD storage 视为简单收纳品

现有数据库离线重处理：

- 总记录：246
- Products：107
- Demand Signals：6
- Software：31
- Inspiration：0
- Uncertain：102
- Product Feasibility PASS：0，REVIEW：69，REJECT：38
- Demand Signals HIGH：3，MEDIUM：1，LOW：2
- 未访问网络，未重新运行 scraper，未删除原始数据

测试结果：

- `pytest`：65 passed

## Phase 6.5 - Feasibility Calibration

状态：  
Completed

完成日期：2026-08-25

修改文件：

- `feasibility_filter.py`
- `db.py`
- `tests/test_feasibility_filter.py`
- `tests/test_pipeline.py`
- `docs/progress.md`

校准内容：

- PASS 重新定义为“从现有信息看无明显硬风险，值得进入供应链/微创新研究”，不表示已证明可生产
- 保留 weapon、complex electronics、wireless、high regulation、large/heavy 和 high engineering barrier 的硬性 REJECT 优先级
- 新增 simple structure、non-electronic、small/compact、common material、simple sewn/plastic/metal product 等可解释正向信号
- titanium、carbon fiber、precision CNC、special mechanism 等特殊材料或工艺优先 REVIEW
- feasibility score 改为连续区分评分，PASS 阈值为 70，硬性 REJECT 不受市场验证信号覆盖
- `positive_signals` 通过兼容迁移持久化，未删除或重建数据库

现有 product 记录离线重算：

- Products：107
- PASS：0
- REVIEW：69
- REJECT：38
- PASS 70–79：0，80–89：0，90–100：0
- Checkpoint PASS 数量：0
- Demand Signal 逻辑和数据未改变
- 未访问网络，未重新运行 scraper

测试结果：

- `pytest`：73 passed

## Phase 6.6 - Reddit Source Expansion

状态：  
Completed

完成日期：2026-08-25

修改文件：

- `config.py`
- `scrapers/arctic_shift.py`
- `tests/test_arctic_shift.py`
- `main.py`
- `tests/test_pipeline.py`
- `docs/progress.md`

社区配置：

- EDC：medium
- ShutUpAndTakeMyMoney：high
- onebag：high
- BuyItForLife：high
- CampingGear：medium_high
- organization：high
- 每社区默认最多20条，主 Pipeline 的 Reddit 总处理上限为120条
- 使用 Arctic Shift `after` 参数限定最近30天，按时间倒序请求
- 每个 subreddit 独立请求，单个社区失败不中断其他社区

真实抓取：

- EDC：20
- ShutUpAndTakeMyMoney：20
- onebag：20
- BuyItForLife：20
- CampingGear：17
- organization：14
- Total Reddit Fetched：111
- 实际新增保存：71
- 已有/URL唯一约束跳过：40
- 失败社区：无

新增记录 Demand Signal 试运行：

- HIGH：3
- MEDIUM：14
- LOW：4
- purchase_intent：6
- product_gap：1
- price_pain：1
- feature_request：4
- usage_problem：0
- recommendation_request：9
- DIY_workaround：0
- HIGH 按社区：onebag 1、BuyItForLife 2，其他社区 0

测试结果：

- `pytest`：78 passed

## Phase 6.7 - Reddit Intent Search

状态：  
Completed

完成日期：2026-08-25

修改文件：

- `config.py`
- `scrapers/arctic_shift.py`
- `main.py`
- `tests/test_arctic_shift.py`
- `tests/test_pipeline.py`
- `docs/progress.md`

意图发现策略：

- 从 latest subreddit sampling 升级为 subreddit + intent-based discovery，优先获取购买需求、产品缺口、价格痛点和功能请求
- 保留小型通用意图库与社区专属意图配置
- Arctic Shift 当前帖子搜索对大型 OR 查询返回空数据或超时，因此每社区使用2个配置化代表意图查询，不按每个关键词单独请求
- 时间窗口扩展为最近90天，每社区最多保留30条，总上限180条
- 跳过 removed/deleted、无有效文本、低信息纯图和重复 URL
- `matched_intents` 和 `intent_source` 保存在 `raw_data`
- 社区权重：EDC low、ShutUpAndTakeMyMoney medium、onebag high、BuyItForLife high、CampingGear medium_high、organization high

真实 Intent Search：

- EDC：Fetched 60，Valid 30
- ShutUpAndTakeMyMoney：Fetched 3，Valid 2
- onebag：Fetched 60，Valid 30
- BuyItForLife：Fetched 30，Valid 30
- CampingGear：Fetched 30，Valid 27
- organization：Fetched 17，Valid 2
- Total Valid：121
- Removed / Invalid skipped：21
- 数据库新增：113
- BuyItForLife 和 CampingGear 各有1个 query 返回 HTTP 422，其他 query 成功，无社区整体失败

新增记录 Demand Signal：

- HIGH：36
- MEDIUM：52
- LOW：5
- HIGH 按社区：EDC 9、ShutUpAndTakeMyMoney 0、onebag 6、BuyItForLife 11、CampingGear 10、organization 0
- Demand Types：purchase_intent 32、product_gap 2、price_pain 2、feature_request 5、usage_problem 0、recommendation_request 51、DIY_workaround 1

测试结果：

- `pytest`：82 passed

## Phase 6.8 - Demand Opportunity Filter

状态：  
Completed

完成日期：2026-08-25

修改文件：

- `demand_opportunity_filter.py`
- `db.py`
- `main.py`
- `tests/test_demand_opportunity_filter.py`
- `tests/test_pipeline.py`
- `docs/progress.md`

分层原因：

- Demand Signal 回答“是否存在真实需求”
- Demand Opportunity 独立回答“该需求是否适合低成本实体商品微创新研究”
- 需求强度不会覆盖大型家电、复杂电子、高监管或高研发品类的资源不匹配
- PRODUCTIZABLE 只表示值得进一步供应链/微创新研究，不表示供应商、成本或生产已验证
- LOW Demand Signal 保留但不进入 Demand Opportunity Filter

数据库与 Pipeline：

- 新增 demand_opportunity_status、demand_opportunity_score、demand_opportunity_reason 和 opportunity_flags 兼容迁移
- Pipeline 增加 Demand Opportunities、Productizable by subreddit 和 Top Opportunity Flags 输出
- 未删除、清空或重建数据库

现有 Reddit HIGH/MEDIUM 离线重处理：

- HIGH + MEDIUM total：107
- PRODUCTIZABLE：26
- REVIEW：70
- NOT_FIT：11
- Productizable by subreddit：EDC 17、ShutUpAndTakeMyMoney 0、onebag 7、BuyItForLife 0、CampingGear 2、organization 0
- Top flags：existing_simple_product 49、portability_problem 44、clear_size_requirement 30、storage_or_organization 29、clear_usage_scenario 27
- Checkpoint PRODUCTIZABLE 数量：15（限制输出数；总数26）
- 未访问网络

测试结果：

- `pytest`：92 passed

## Phase 7 - Micro-Innovation Candidate Pool

状态：  
Completed

完成日期：2026-08-25

修改文件：

- `candidate_pool.py`
- `db.py`
- `main.py`
- `tests/test_candidate_pool.py`
- `tests/test_pipeline.py`
- `docs/progress.md`

统一候选层：

- Validated Product 提供“已存在明确商品并通过个人可执行性”的机会
- Demand Opportunity 提供“用户明确提出成熟商品的具体缺口”的机会
- 两条路径保留各自证据与评分，统一转换为 `MicroInnovationCandidate` 以支持后续供应链研究
- 候选层不改写原始 Product，不表示供应商、成本或生产已验证

评分与持久化：

- Demand Opportunity：Demand明确度35%、个人可执行性35%、微创新空间30%
- Validated Product：个人可执行性40%、市场验证35%、微创新空间25%
- backers 使用分段平滑评分，percent_funded 仅作辅助，未使用 `>=300%` 二元标签
- 新增 `micro_innovation_candidates` 表，candidate_id 和 source_url 唯一去重
- 未删除或改写 products 表历史数据，未访问网络

当前候选池：

- Validated Product Candidates：5（均为数据库中真实 feasibility PASS 的 Reddit onebag 记录）
- Kickstarter Validated Product Candidates：0
- Demand Opportunity Candidates：26
- Total Candidates：31
- Candidate Score 90–100：2，80–89：1，70–79：8，<70：20
- Top Candidate Sources：Reddit EDC 17、Reddit onebag 12、Reddit CampingGear 2、Kickstarter 0
- Checkpoint Top Candidates：20

测试结果：

- `pytest`：99 passed

## Phase 7.1 - Candidate Pool Audit

状态：  
Completed

完成日期：2026-08-25

- Phase 7.1 Candidate Pool Audit generated.
- 以只读方式审计全部 31 条 `micro_innovation_candidates`。
- 生成 `docs/candidate_audit.md`，包含来源分榜、单一主题归类和简单关键词相似机会分组。
- 未访问网络，未调用 AI，未修改数据库、评分规则或业务代码。

Phase 7.2A Creative Product Source Probe completed.

## Phase 7.2B - Yanko Design Creative Product Integration

状态：  
Completed

完成日期：2026-08-25

- 使用公开 RSS `https://www.yankodesign.com/feed/`，未逐篇访问文章页面，未加入每日完整 Pipeline。
- Fetched：10；New：10；Duplicates：0。
- Content Types：physical_product 3、concept_product 1、architecture 0、vehicle 1、technology_complex 5、other 0。
- Eligible Inspiration Products：1；新增 Inspiration Candidates：1。
- Candidate Pool：Validated Product 5、Demand Opportunity 26、Inspiration Product 1、Total 32。
- Candidate Diversity：bags_and_carry 从 13 / 31 变为 13 / 32。
- `market_validation_score` 保持 0；未虚构市场验证。
- `pytest`：110 passed。

Phase 7.3A Indiegogo Official Public API Probe completed.

Phase 7.4A Amazon Consumer Trend Source Probe completed.

Phase 7.4B Keepa Cost & Capability Probe completed.

## Phase 7.4C - Amazon Lightweight Consumer Trend MVP

状态：  
Completed

完成日期：2026-08-25

- 新增轻量 Amazon 趋势采集模块，仅使用公开榜单 HTML，不访问商品详情页，未加入默认 Pipeline。
- 独立真实验证共发出 3 次请求：New Releases 成功 1 页，Movers & Shakers 失败 1 页（含一次轻量重试）。
- Fetched：30；New Releases：30；Movers & Shakers：0。
- 免费预筛结果：Simple Physical 7、Rejected 10、Uncertain 13。
- 新增 Consumer Trend Candidates：7；评分使用可执行性 40%、公开榜单市场信号 35%、微创新空间 25%，不代表销量验证。
- `pytest`：127 passed；Phase 7.4C 相关复核：35 passed。

## Phase 7.4D - Commodity & Red-Ocean Filter

状态：  
Completed

完成日期：2026-08-25

- 新增成熟普通商品与红海风险预筛选：简单、可生产的实体商品不等于值得进入微创新研究。
- Commodity 判断仅使用当前商品文本中的差异化与成熟品类信号；rank、rating、review_count 和 New Releases 身份不提高 commodity_score。
- Amazon Consumer Trend 仅允许 `PROMISING` 自动进入候选池；`REVIEW` 和 `COMMODITY` 结果保存在 products 表，不影响 Reddit、Kickstarter 或 Yanko。
- 对 Phase 7.4C 原有 7 条 Amazon 候选离线重算：PROMISING 1、REVIEW 3、COMMODITY 3。
- 识别 10x10 canopy 为 `bulky_shipping`；食品接触容器不会仅因 food/container 表述被视为可食用商品。
- `pytest`：139 passed。

## Phase 8.1 - AI Cheap Triage Foundation

状态：  
Completed

完成日期：2026-08-25

- AI 仅分析 Candidate Pool；不接收完整 raw_data、HTML 或外部网页内容。
- 默认并实际使用 deterministic Mock 模式，没有实现或调用任何真实付费 AI Provider。
- 新增严格 `AITriageResult`、Provider 抽象、20 条批次上限、多 candidate type 轮转选择和 candidate_id 去重成本保护。
- 新增独立 `ai_triage_results` 表，保留现有数据库历史数据。
- Mock Validation：Eligible 33、Selected 20、Skipped 0、Processed 20、PASS 6、REVIEW 11、REJECT 3、Errors 0。
- 输入字符数：平均 941.0，最大 1094；description 最大 500 字符。
- `pytest`：148 passed。

Phase 8.1 AI Cheap Triage Foundation completed.

## Phase 8.1A - OpenAI Provider Readiness

状态：  
Completed

完成日期：2026-08-25

- 新增 OpenAI Responses API Provider 准备层，使用 Structured Outputs JSON Schema；默认 AI Mode 保持 mock。
- 默认模型集中配置为 `gpt-5.4-nano`，支持环境变量替换；API Key 不打印、不写入示例值。
- 30 秒超时、最多一次轻量重试，鉴权错误不重试；单条 Provider 错误不破坏 batch。
- 新增最多 5 条、多 candidate type 的显式未来真实验证入口；本阶段未执行。
- OpenAI Dry Run：Configured no、Selected 5，类型覆盖 validated_product、demand_opportunity、inspiration_product、consumer_trend；平均输入 899.6 字符，最大 1047，Request Ready yes，Network Request Sent NO。
- `pytest`：155 passed。

Phase 8.1A OpenAI Provider Readiness completed.

## Phase 8.1B - Gemini Provider Readiness

状态：  
Completed

完成日期：2026-08-25

- 新增官方 Google GenAI SDK Provider 准备层，默认模型为 `gemini-2.5-flash-lite`；默认 AI Mode 保持 mock。
- Gemini、OpenAI、Mock 共用相同 System Prompt、Candidate Input Builder、Structured Output Schema 和结果验证。
- Gemini 使用 30 秒超时、最多一次轻量重试，鉴权错误不重试；单条错误不会破坏 batch。
- 新增最多 5 条、多 candidate type 的未来 Gemini 真实验证入口；本阶段未执行。
- Gemini Dry Run：Configured no、Selected 5，类型覆盖 validated_product、demand_opportunity、inspiration_product、consumer_trend；平均输入 899.6 字符，最大 1047，Request Ready yes，Network Request Sent NO。
- `pytest`：160 passed。

Phase 8.1B Gemini Provider Readiness completed.

## Phase 8.1C Blocker Fix - AI Triage Result Uniqueness

状态：  
Completed

完成日期：2026-08-25

- Phase 8.1C blocker fixed.
- `ai_triage_results` 唯一键由 `candidate_id` 安全迁移为 `candidate_id + provider + model`。
- 迁移采用新表复制、数量校验和替换流程；20 条历史 Mock 结果全部保留。
- 同一 Candidate 现在可并存 Mock、Gemini、OpenAI 及不同模型结果；force reanalyze 只更新完全相同的 Provider/Model 记录。
- `pytest`：163 passed。

## Phase 8.1C Network Blocker

状态：  
Blocked

日期：2026-08-25

- Gemini connectivity unresolved.
- `google-genai` SDK timeout 已明确配置为 15000 毫秒，SDK 隐式 retry 已限制为 1 次总 attempt；项目层仍最多一次轻量 retry。
- 新增 20 秒单请求 wall-clock 上限。
- 最小 Connectivity Check 在 0.31 秒返回 `ClientError status 400`，未执行 Candidate 测试，未保存 Gemini Result。
- 只读网络诊断：DNS 可解析；直接 HTTPS 443 检查超时；未检测到 HTTP/HTTPS Proxy 或自定义证书环境变量。
- `pytest`：167 passed。

## Phase 8.1C - Gemini Model Migration

状态：  
Blocked by connectivity

日期：2026-08-25

- Gemini default triage model migrated: `gemini-2.5-flash-lite` → `gemini-3.5-flash-lite`。
- `config.py` 是默认模型唯一配置源；`.env.example` 和 Gemini 文档已同步，未修改真实 `.env`。
- `pytest`：167 passed；OpenAIProvider 与 MockProvider 测试继续通过。
- TEST A Plain Text：使用 `gemini-3.5-flash-lite` 发出 1 次请求，15.62 秒后返回 `ServerError 504: Deadline expired before operation could complete.`。
- TEST B 未执行；未发送 Structured Output 请求，未发送 Candidate 数据。

## Phase 8.1D - Gemini Single Candidate Real Triage

状态：  
Blocked by Gemini structured-output request error

日期：2026-08-25

- Candidate：`Fanny pack without zipper`。
- Model：`gemini-3.5-flash-lite`。
- Status：请求返回 `ClientError status 400`，未生成或保存 Gemini Triage Result。
- Score：unavailable。
- Usage：unavailable。
- Elapsed time：0.30 seconds。

## Phase 8.1D - Gemini Schema Compatibility Fix

状态：  
Completed

日期：2026-08-25

- Gemini schema compatibility fixed：OpenAI 继续使用 raw JSON Schema，Gemini 改用独立 Pydantic response schema。
- Gemini response schema 移除不兼容的 `additionalProperties` 及长度、数量、数值约束；统一结果转换层继续执行安全规范化。
- `pytest`：171 passed。
- 完整 Structured Output 测试：HTTP 200，2.03 seconds。
- 真实 Candidate：`Fanny pack without zipper`，Gemini `PASS` / 10，2.00 seconds。
- Usage：input 364、output 124、total 488 tokens；Gemini 结果已保存，Mock 结果保留。

## Phase 8.1E - AI Triage Grounding Guardrails

状态：  
Completed

日期：2026-08-25

- 真实 Gemini 测试曾产生未经输入支持的 supplier/MOQ 与 user-segment 确定性推断；System Prompt 已增加事实边界约束。
- Grounding 规则要求供应链、成本、竞争、市场、用户画像、IP、认证和监管结论必须来自 Candidate Input；假设需明确使用不确定性语言并要求验证。
- `pytest`：172 passed。
- `Fanny pack without zipper` 重新分析：Gemini `PASS` / 8，unsupported claims 简单检查为 no。
- Usage：input 517、output 195、total 712 tokens；elapsed 1.88 seconds；Mock 结果保留。

## Phase 8.1F - Gemini 5-Candidate Diversity Validation

状态：  
Completed

日期：2026-08-25

- Selected：5；candidate types：2 demand_opportunity、1 validated_product、1 inspiration_product、1 consumer_trend。
- Gemini model：`gemini-3.5-flash-lite`；successful 5、failed 0。
- 结果分布：PASS 3、REVIEW 0、REJECT 2。
- Usage：input 2634、output 822、total 3456 tokens；average 691.2 tokens/candidate。
- 指定关键词规则检测到的 unsupported claims：0。

## Phase 8.2A - Deep Analysis Design

状态：  
Completed

日期：2026-08-25

- Phase 8.2A Deep Analysis Design completed.
- 新增 Deep Analysis 的目的、输入、统一输出结构、四类 Candidate 差异、Grounding、Token Budget、Provider 调用、数据库版本键和执行流程设计。
- 本阶段 API calls：0；未修改业务代码、数据库、Cheap Triage Prompt 或 Pipeline。

## Phase 8.2B - Deep Analysis MVP

状态：  
Completed

日期：2026-08-25

- 实现 Physical Deep Analysis MVP、Gemini-compatible Pydantic structured output、2,500-character 输入预算和 Grounding 检查。
- Candidate：`[Comparison] I tested out and compared 5 good backpacking pillows so you don't have to.`。
- Deep Score：7；Recommended Next Step：`VALIDATE_SUPPLIER`；analysis version：`v1`。
- Usage：input 920、output 897、total 1817 tokens；elapsed 41.78 seconds；input characters 2464。
- Grounding Check：指定关键词规则未检测到 unsupported claims；结果已保存到独立版本化表。
- `pytest`：182 passed。
- 长期最终输出规则：Daily Top 10、Physical-first、Software <=2、No Forced Fill。

## Phase 8.2C - Deep Analysis Calibration

状态：  
Completed

日期：2026-08-25

- Deep Analysis Prompt 校准：加强 hypothesis、供应链/成本、existing solution gap 和 feasibility 的 Grounding，输出目标调整为 500-700 tokens、上限目标 800。
- Backpacking Pillow v2：Deep Score 5；Recommended Next Step `VALIDATE_SUPPLIER`；v1 保留。
- v2 Usage：input 1109、output 825、total 1934 tokens；实际输出比 800-token 目标高 25 tokens。
- 无验证供应商/成本数据时，startup cost 与 manufacturing complexity 的 LOW 返回后规范化为 UNKNOWN。
- Grounding 简单检查：unsupported supply no、cost no、market yes（未验证的 market dominance 表述）。
- `pytest`：183 passed；最终 Deep Analysis 专项测试：11 passed。
- Daily Rule 保持：Top 10、Physical First、Software <=2、No Forced Fill。

## Phase 8.2D - Physical Deep Analysis Final Grounding Fix + Lightweight Software Analysis Design

状态：  
Completed

日期：2026-08-25

- Physical Deep Analysis market grounding finalized：多个品牌、产品比较、评论和排名不再被扩展为 dominated、saturated、low competition 或 market growth 结论。
- Physical Deep Analysis v2 finalized；本阶段未重新调用 Gemini。
- 新增 Lightweight Software Analysis 设计，独立于实体商品的供应链、制造和物流字段；input <=2000 characters、output <=500 tokens。
- Daily Top 10 保持 Physical First、Software <=2、No Forced Fill。
- API calls：0。
- `pytest`：185 passed。

## Phase 8.2E - Lightweight Software Analysis MVP

状态：  
Completed

日期：2026-08-25

- 实现独立 Lightweight Software Analysis Pydantic Schema、2,000-character 输入预算、Grounding 检查和版本化 `software_analysis_results` 存储。
- Candidate：`App that recommends smart fabric choices for one-bag travel based on destination and weather?`。
- Software Score：10；Recommended Next Step：`VALIDATE_DEMAND`；analysis version：`v1`。
- Usage：input 568、output 674、total 1242 tokens；elapsed 3.14 seconds；input characters 1153。
- Grounding Check：指定关键词规则未检测到 unsupported claims；实际输出高于 500-token 设计目标。
- `pytest`：193 passed；Physical Deep Analysis 不受影响。
- Daily Final Rule 保持：Top 10、Physical First、Software <=2、No Forced Fill。

## Phase 8.2F - Software Score Calibration + Analysis Layer Finalization

状态：  
Completed

日期：2026-08-25

- Software Score 已按 evidence strength、demand validation、monetization evidence、retention risk、competition unknowns 和技术依赖进行校准；Score 10 设为极罕见。
- 技术简单、低基础设施成本和高 solo-builder fit 不再被视为商业验证。
- 保留 Phase 8.2E software analysis v1 历史结果；本阶段 API calls：0。
- Analysis Layer：Cheap Triage finalized、Physical Deep Analysis finalized、Lightweight Software Analysis finalized、Grounding finalized。
- Daily Final Rule：Top 10、Physical First、Software <=2、No Forced Fill。
- Next Phase：Daily Opportunity Ranking + Final Top 10。
- `pytest`：194 passed。

## Phase 9.1 - Daily Opportunity Ranking Engine

状态：  
Completed

日期：2026-08-25

- 新增透明的 0-100 Daily Ranking：AI Quality、Evidence、Feasibility、Actionability、Cross Source、Freshness。
- 实现 PASS 质量门、已有 hard-risk 排除、Physical First、Software <=2、Theme <=3、near-duplicate 和 No Forced Fill。
- 当前数据库 Dry Run：Eligible 7、Rejected 67、Physical Eligible 7、Software Eligible 0、Final Count 7。
- 去重移除 0、主题配额移除 0、软件配额移除 0；未调用 Deep Analysis 或任何 API。
- `pytest`：204 passed。
- 新增规则审计文档 `docs/daily_ranking_design.md`。

## Phase 9.2 - Daily Ranking Triage Coverage Expansion

状态：  
Completed

日期：2026-08-25

- 选择 20 条候选补充 Gemini Cheap Triage：Physical 16、Software 4；已有同模型结果按组合键跳过。
- API HTTP attempts 22（2 条触发各一次允许的 retry）；successful 18、failed 2、skipped existing 0。
- 结果：PASS 11、REVIEW 3、REJECT 4；usage input 9573、output 3164、total 12737 tokens。
- Daily Ranker 现明确区分 `missing_triage`、`triage_review`、`triage_reject`，并提供不覆盖原始标题的 display title fallback。
- 重新 Ranking：Eligible 15、Physical Eligible 15、Software Eligible 0、Final Count 10。
- 保持 Physical First、Software <=2、No Forced Fill；Deep Analysis calls 0。
- `pytest`：207 passed。

## Phase 9.2A - Final Opportunity Specificity Gate

状态：  
Completed

日期：2026-08-25

- 在 Daily Ranking 质量门之后增加免费、透明的商品机会具体性门槛，不改变 Phase 9.1 排名权重。
- 当前数据库结果：SPECIFIC 11、REVIEW 2、TOO_BROAD 2；进入具体性门槛前 15 条，移除 2 条，暂缓 2 条，最终可排名 11 条，Daily Top 8 条。
- Physical `demand_opportunity` 的 REVIEW 暂缓、TOO_BROAD 移除；其他明确 Physical Candidate Type 不被该门槛误杀；Software 排名逻辑保持不变。
- `pytest`：216 passed；AI/API calls：0。

## Phase 9.3 - Finalist Deep Analysis

状态：  
Blocked

日期：2026-08-26

- Finalists before Deep Analysis：8；selected missing v2：7；skipped existing v2：1。
- Gemini `gemini-3.5-flash-lite` 首轮 7 次与获准的最后一次 retry 7 次均触发 65 秒 wall-clock limit；成功 0，未保存失败结果，也未执行第三次尝试。
- 根因暂记：Gemini Deep Analysis timeout blocker。Prompt、Schema、Provider timeout 和 Deep Analysis 评分逻辑均未修改。
- Final Deep Gate：7 条 `analysis_failed`；已有 Backpacking Pillow v2 因 unsupported claim 进入 Human Review。PASS 0、REVIEW 0、DROP 0、Human Review 8；Final Daily Count 0，未补位。
- `pytest`：222 passed。

## Phase 9.4 - Daily Report Foundation

状态：  
Completed

日期：2026-08-26

- Deep Analysis 已调整为 optional / on-demand；缺失、timeout 或不可信的分析回退 Cheap Triage，不再阻断日报。
- 有效 Physical/Software Analysis 仍优先；明确 `DROP` 或现有 hard risk 仍可排除。Phase 9.1 排名权重保持不变。
- 新增 `DailyReportItem`、`DailyReport` 与纯 HTML/inline CSS 本地报告生成器。
- 当前数据库日报：Total 8、Physical 8、Software 0、Deep Analyzed 0、Cheap Triage Fallback 8。
- 生成 `reports/2026-08-26-product-picker.html`；API calls：0。
- `pytest`：228 passed。

## Phase 9.5 - Bilingual Full Opportunity Feed

状态：  
Completed

日期：2026-08-26

- 日报改为中英双语 Full Qualified Opportunity Feed；Top Picks 继续最多10条并保留 Theme/Software 配额，Full Feed 不受这些展示配额或最低排名分隐藏。
- 当前真实数据：Top Picks 8、All Qualified 11、Physical 11、Software 0、Inspiration/Trend 1。
- 来源分布：Reddit 10、Amazon 1、Yanko Design 0、Product Hunt 0、Kickstarter 0、Indiegogo 0。
- Software Funnel：Total 42、PASS 0、REVIEW 0、REJECT 2、MISSING 40、Qualified/Displayed 0；Software=0 不是 Physical First 或 Software quota 导致。
- 生成 `docs/daily_source_audit.md`、`docs/software_funnel_audit.md`，并更新 `reports/2026-08-26-product-picker.html`。
- API calls：0；`pytest`：234 passed。

## Phase 9.5B - Data Foundation Upgrade

状态：  
Completed

日期：2026-08-26

- 六个核心来源均进入默认 Pipeline：Reddit/Arctic Shift、Amazon、Kickstarter/KSInsights、Indiegogo、Yanko Design、Product Hunt。
- 新增 Indiegogo 官方公开 API scraper；真实运行获取并保存 100 条，无需 API Key。
- Products 生命周期新增 first_seen/last_seen/updated；重复 URL 更新当前公开数据并保留首次发现时间。
- 新增动态指标快照、Pipeline/source run tracking、Specificity v1 持久化、人工反馈和重新评估请求表。
- 安全 migration：Products 484→484，Candidates 33→33，AI 44→44，Deep 2→2，Software Analysis 1→1；随后真实六源运行 Products 增至653、Candidates增至44。
- 当前 metric snapshots 230；44 个当前 Candidate 已回填 Specificity v1。
- 数据保留验证：Rule/Feasibility/Commodity/Gemini REVIEW/REJECT、Software 数据均保留。
- `pytest`：242 passed；Gemini API calls：0。

## Phase 9.6

Status: Coverage blocker

Multi-Source Candidate Coverage Completion rebuilt the offline Candidate Pool from 653 stored products without scraping. Gemini Cheap Triage found 71 missing results; processing stopped after three consecutive real API failures as required (0 successful, 3 failed, 68 not attempted). Existing results were preserved. Specificity v1 results were persisted for eligible physical demand opportunities, and the full bilingual qualified feed plus source/software audits were regenerated. pytest: 245 passed.

### Phase 9.6 Resume

Status: Coverage blocker

Network recovery was reported and Cheap Triage coverage resumed without scraping or reanalysis. The database still contained 71 missing Gemini results. The first three candidates again failed at the existing request limit, so processing stopped after 3 API calls as required: 0 successful, 3 failed, 68 not attempted. Existing Gemini results remained unchanged. The bilingual report and source/software audits were regenerated from current stored results. `pytest`: 245 passed; Deep Analysis calls: 0.

### Phase 9.6C Database Consistency Quick Check

Status: Completed

- Runtime database: `D:\系统默认\桌面\Product picker\data\product_picker.db`; no other `product_picker.db` copy exists under the project root.
- SQLite `products` contains 653 rows and two consecutive read-only counts both returned 653; `PRAGMA integrity_check` returned `ok`.
- The earlier 628 figure was `len(db.get_all_products())`, not the database row count. That loader intentionally skips invalid legacy rows; 25 `reddit_arctic_shift` rows have an empty `description` and fail the current `Product` validation, so 653 stored rows minus 25 skipped rows equals 628 loaded Product objects.
- Existing products, candidates, Gemini triage, physical deep analysis, and software analysis records remain preserved.
- Gemini Missing remains 71. Missing Gemini triage is represented as AI Pending/MISSING and no longer blocks Product Picker Web App development.
- `pytest`: 245 passed; Gemini API calls: 0; scraper calls: 0.

## Phase 9.7 - Product Picker Web App MVP

状态：
Completed

日期：2026-08-26

- 新增本地 Streamlit Web App，包含 Today、All Products、Software、Favorites、Watchlist、Rejected/Archive 六个双语页面。
- 修复 legacy empty description 读取兼容，不修改原始数据库内容；Web App 可读取 SQLite 中全部653条 Products。
- 新增统一 Dashboard 数据快照、关键词/来源/日期/类型/规则/AI/人工状态筛选和分页。
- `FAVORITE`、`WATCH`、`NOT_INTERESTED` 持久化且互斥；`RE_EVALUATE` 独立进入待处理队列，不调用AI。
- AI Missing 正式显示为 `AI_PENDING`，不会被隐藏或视为拒绝。
- 支持 Metric History、最新 Pipeline Source 状态以及安全的 Deep/Software Analysis 摘要展示；不暴露 raw_data、Prompt、Key 或数据库路径。
- 新增 `docs/web_app_design.md` 和 `docs/web_app_setup.md`；本阶段 Gemini API calls 0、scraper calls 0。

### Phase 9.7A - Web App UX Fix

状态：  
Completed

- Sidebar-only navigation replaced by six always-visible top tabs.
- All Products now opens as the complete 653-record database browser with an immediate search box, visible Source/Date/Type/AI/Filter/My Status controls, result count, and 50-record Previous/Next pagination.
- Cards now use Chinese-first fixed labels with English comparison text, known deterministic Chinese title mappings, and honest missing-Chinese fallbacks for dynamic AI content.
- Rejected Archive includes bilingual retention guidance; all feedback controls are bilingual.
- Runtime search smoke: `bathroom` matched 2 stored records and `backpack` matched 50.
- `future_bilingual_ai_output = planned`; no Prompt or schema change and no Gemini/scraper calls.

### Phase 9.7B - Bilingual AI Content Foundation

状态：  
Completed

- Cheap Triage structured output now includes `display_title_zh`, `primary_reason_zh`, `key_opportunity_zh`, and `main_risks_zh` while preserving every existing decision/English field.
- Prompt requires English and natural Simplified Chinese in one grounded response; Chinese cannot add facts or certainty absent from evidence/English.
- Safe SQLite migration adds nullable bilingual columns without rebuilding the table or changing the `(candidate_id, provider, model)` unique key. Existing 44 total AI rows and 24 real Gemini rows are preserved.
- Web App display priority is persisted Chinese → deterministic mapping → original English; missing dynamic Chinese uses compact `待补充` followed by English.
- Added translation-only backfill selection/merge protection. Current eligible real Gemini rows: 24; status and score cannot be changed by enrichment.
- Normal historical Products are not batch translated. Software bilingual fields are design-only reserved; Deep Analysis Prompt remains unchanged.
- Gemini API calls: 0; scraper calls: 0.

### Phase 9.8A - Cloud Deployment Readiness

状态：  
Completed

- Web与定时Pipeline入口分离；`app.py`不触发抓取，`run_daily.py`不依赖Streamlit。
- 新增`DATABASE_URL`后端边界：未配置继续使用SQLite；PostgreSQL URL已识别，正式驱动留待部署阶段。
- Gemini不可用时运行状态为`PARTIAL`，产品不回滚，缺失分析保留为`AI Pending`。
- 新增全历史SQLite→PostgreSQL schema计划及只读dry-run；当前653条Products与候选、AI、分析、指标、运行、反馈均在范围内。
- 新增单实例Pipeline lock、UTC/Asia-Tokyo时间帮助、源码密钥扫描及英文优先双语降级。
- 对比Render、Railway、Streamlit Community Cloud + 外部PostgreSQL；建议部署前优先复核Render。
- 未执行PostgreSQL migration或云部署；Gemini API calls 0、scraper calls 0。

### Phase 9.7D/E - Product Information Layer + Bilingual Layout Refinement

状态：  
Completed

- 建立独立的Product Information、Source Evidence、AI Opportunity Analysis三层展示结构。
- 653条Products均可通过description、公开source metadata或title生成非AI Product Summary；16条六来源抽样均可仅凭标题和梗概理解。
- 正式区分`NOT_ANALYZED`与`AI_PENDING`，无真实AI结果时不再显示三个空分析栏目。
- Meta、Product Summary与AI Analysis改为完整English block后接完整中文block；每个缺失区域最多一个紧凑pending标签。
- Today保留既有日报确定性中文内容；All Products默认保持紧凑，AI详情进入expander。
- Reddit、Amazon、Kickstarter、Indiegogo、Product Hunt与Yanko Design均支持白名单Source Evidence，raw_data不直接展示。
- 本地Streamlit smoke test：HTTP 200、6 tabs、0 app exceptions；`pytest`: 290 passed。
- Gemini API calls 0、scraper calls 0；未启动云部署或PostgreSQL迁移。

### Phase 9.7F - Bilingual Fallback Cleanup + Production Data Hygiene

状态：  
Completed

- 删除Web App统一伪中文AI模板；仅持久化`*_zh`字段可作为真实中文AI内容，旧英文结果只显示一次中文分析pending。
- 中文Product Summary缺失时只显示一次紧凑pending；英文Summary完整保留。
- 正文保持English完整块后接中文完整块；标题与互动按钮继续紧凑双语。
- 新增production migration只读分类：真实来源Products 652 KEEP / Test记录1 SKIP；Metric Snapshots 230 KEEP。
- Gemini 24 KEEP、Mock 20 SKIP、Specificity 44 KEEP；验证期Deep 2、Software 1及开发feedback 1均标记TEST_ONLY并SKIP。
- `--dry-run --production-only`已验证，不连接PostgreSQL、不修改或删除SQLite记录。
- Gemini API calls 0、scraper calls 0；云部署未启动。

### Phase 9.8B - Zero-Cost Cloud Deployment Package

状态：  
Completed

- 确定Private GitHub + GitHub Actions + Streamlit Community Cloud + Neon PostgreSQL目标架构；未创建或部署任何外部资源。
- 实现`DATABASE_URL`自动选择SQLite/PostgreSQL、psycopg连接池、正式PostgreSQL schema、JSONB/TIMESTAMPTZ/BOOLEAN及Dashboard索引。
- Web与Daily Pipeline继续共用db接口；Web不触发抓取，GitHub Actions运行`run_daily.py`。
- 新增production-only PostgreSQL迁移执行路径、identity sequence重置与逐表数量一致性检查；本阶段仅运行dry-run。
- GitHub Actions支持手动触发和08:00 JST（23:00 UTC）schedule；schedule默认受`DAILY_SCHEDULE_ENABLED`保护。
- Streamlit仅需`DATABASE_URL`；GitHub Actions使用`DATABASE_URL`和`GEMINI_API_KEY`。
- 新增云端read-only/feedback健康检查入口及Neon、Streamlit、GitHub Actions逐步文档。
- Gemini API calls 0、scraper calls 0、真实Cloud deployment未开始。

### Phase 11B - Evidence-First Data Foundation / Shadow Mode

状态：Completed in shadow mode

- 在不改变现有UI、WxPusher、Candidate、Gemini与Ranking生产路径的前提下，新增可同时用于SQLite/PostgreSQL的增量Shadow schema。
- 旧路径保持：`Source → Candidate → Gemini → Qualified → Top Picks`。
- 新Shadow路径：`Source → Observation → Eligibility → Product Identity → Product Family → Evidence → Daily Discovery`。
- `product_observations`以Pipeline Run为成员边界，不再使用`first_seen_at`推断Today；历史Observation仅在run时间区间和source ledger共同支持时回填。
- Eligibility只判断来源记录中是否存在可识别的实体、软件或产品设计，不判断商业价值；明显电影/活动内容保留原Product但从Daily Discovery排除。
- `products.title`继续保持原语义；标准化名称和中文名称进入独立、版本化identity表，无法可靠识别时保持unresolved。
- Product Family使用保守的确定性blocking/token/synonym规则，原始Product及其URL/raw_data始终保留。
- Evidence仅提取已存储的来源事实；WEAK/MODERATE/STRONG表示证据量，不是机会分或销售建议。
- Daily Discovery返回最新已完成run中全部Eligible Family，不受Top-N、Gemini PASS或Qualified限制。
- AI未被删除；未来职责是翻译、歧义身份识别和真实证据摘要，不是最终商业裁判，也不是Eligibility/Daily Discovery的必要Gate。
- 现有Product级Favorite/Watch/Not Interested和re-evaluation历史不迁移、不删除；Family层可只读投影已有Favorite。
- 本阶段未调用Gemini、未抓取外部来源、未调用WxPusher，生产UI与生产通知未切换。

### Phase 11C - Product Discovery Quality Gate

状态：Completed in shadow mode

- 明确区分`ELIGIBLE`与可发现性：只有`eligibility_status=ELIGIBLE`且`concrete_product_status=CONCRETE`的来源记录才能进入Daily Discovery。
- 新增版本化Concrete Product Gate，按来源排除trip report、itinerary、通用建议、宽泛brainstorm、multi-item EDC、listicle、客服投诉、电影/活动等噪声；原始Product与证据仍完整保留。
- 名称规范化升级为来源感知：Amazon目录标题压缩为品牌/型号+核心产品名，Reddit问题提取具体产品名，Product Hunt保留品牌并添加简短软件类型，Yanko提取具体设计对象。
- Family canonical name优先人工override，其次最高置信度、最短且信息充分的normalized identity；旧grouping记录以`INACTIVE`保留审计历史，不物理删除。
- Shadow Daily Discovery继续基于最新Run Observation、Family和事实Evidence，不要求Candidate、Gemini、Qualified、Final Score或Top-N。
- 新规则降低trip report、泛讨论、listicle与多商品噪声，同时保留所有raw_data、旧AI/Ranking数据和Product级反馈。
- 未来来源路线：Priority 1 Etsy；Priority 2 Hacker News/Show HN、软件类Reddit扩展、Design Milk；Priority 3 GitHub；Core77需先做access/feed probe；Designboom后续复核。
- 所有未来来源必须走`Source → Observation → Eligibility → Concrete Product Gate → Product Identity → Product Family → Evidence → Daily Discovery`，不得重新以`Candidate → Gemini → Qualified`作为主要可见性Gate。
- 本阶段未切换Streamlit/WxPusher、未新增来源、未调用Gemini或外部scraper。

### Phase 11D - Clean Production Reset + Fresh Evidence-First Validation

状态：Prepared; production audit/reset not yet executed

- 新增仅允许`workflow_dispatch`的生产审计/重置工作流；无cron，且与Daily Pipeline共用concurrency group，避免同时写入。
- 第一轮必须选择`audit`，只读检查Neon schema、约束、索引、外键、表计数以及Favorite Product完整性。
- `reset_and_validate`必须输入精确确认词；在同一事务中创建Neon archive schema并逐表核对备份行数，备份失败或Favorite不完整时自动回滚并停止。
- 重置仅保留Favorite Product、原始source/raw_data、Identity、必要Family关系和事实Evidence；删除其他旧Product及旧Candidate/AI/Ranking/Observation/Run状态，不DROP表或schema。
- Fresh validation关闭Gemini与WxPusher凭据，只运行当前六个来源一次；Today仍严格由最新run的`product_observations`决定，历史Favorite不会自动进入Today。
- 完整Daily Discovery、20条NON_CONCRETE、20条AMBIGUOUS、可疑通过、Family/Evidence审计均输出为GitHub Actions artifact，保留30天。
- 当前只准备代码；在用户通过GitHub Desktop提交并推送前，不执行生产audit/reset。
- Phase 11E来源路线保持：Priority 1 Etsy；Priority 2 Hacker News/Show HN、软件类Reddit、Design Milk；Priority 3 GitHub；Core77条件probe；Designboom后续复核。
