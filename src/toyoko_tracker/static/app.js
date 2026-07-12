            // 防止 /status 覆盖用户正在编辑的表单
            let BLOCK_REMOTE_OVERWRITE = false;
            const EDIT_TS = {};
            let PROGRESS_ANIM_FRAME = null;
            let LAST_PROGRESS_STATE = null;
            function markEdited(id){ EDIT_TS[id] = Date.now(); }
            function recentlyEdited(id, ms=10000){ return EDIT_TS[id] && (Date.now() - EDIT_TS[id] < ms); }
            const UI18N = {
              zh_cn: {
                appName: '东横酱 / Toyoko Chan',
                language: '语言 / Language', runSettings: '运行配置 / Run Settings', search: '搜索 / Search',
                searchTitle: '空房检索条件', searchSubtitle: '选择日期、入住条件和酒店范围；启动后会自动写入搜索记录。',
                tonight: '今晚 / Tonight', tomorrow: '明晚 / Tomorrow', weekend: '周末 / Weekend',
                checkin: '入住 / Check-in', checkout: '退房 / Check-out', people: '人数 / People', rooms: '房间 / Rooms',
                smoking: '吸烟 / Smoking', roomType: '房型 / Room Type', membership: '会员状态 / Membership',
                areaPicker: '区域酒店搜索 / Area Hotel Picker', region: '大区域 / Region', detailArea: '详细区域 / Detail Area',
                loadHotels: '加载酒店 / Load Hotels', selectAll: '全选 / Select All', selectNone: '全不选 / Select None',
                areaHint: '选择大区域；详细区域可不选，默认加载整个大区域。勾选酒店后直接点击 Start 搜索。',
                areaSelected: '已选择大区域；可直接加载全部，或选择详细区域。勾选酒店后直接点击 Start 搜索。',
                selectRegion: '请选择 / Select Region', selectRegionFirst: '先选择大区域 / Select a region first',
                filterPlaceholder: '过滤酒店主语言/英文名或编号 / Filter by primary/English hotel name or code',
                noHotels: '尚未加载酒店 / No hotels loaded yet', noMatchingHotels: '没有匹配酒店 / No matching hotels',
                openMap: '打开地图 / Open Map', history: '搜索记录 / Search History', refresh: '刷新 / Refresh', clear: '清空 / Clear',
                historyHint: '最多显示最近 10 条；完全相同设定不会重复记录。', noHistory: '暂无搜索记录 / No history yet',
                searchSettings: '搜索设定 / Search Settings', pushSettings: '推送设定 / Push Settings',
                engine: '引擎 / Engine', scanCadence: '检索节奏 / Scan Cadence', smartParallel: '智能并行 / Smart Parallel',
                resultTitle: '搜索结果 / Search Results', pushStatus: '推送状态 / Notification Status',
                noData: '暂无结果 / No data yet', start: '启动 / Start', stop: '停止 / Stop', defaults: '默认 / Default',
                testNotification: '发送测试通知 / Test Notification',
                searchSettingsNote: '引擎、检索节奏和智能并行集中在这里。智能并行仅用于 HTTP/API，并会错峰请求。',
                pushSettingsNote: '空房、重复提醒、无房变化和启动通知会发送到所有已启用渠道。',
                searchEngine: '检索引擎 / Search Engine', engineHelp: 'HTTP/API 请求更少更快；失败时会尝试回退 Playwright。',
                enableSmartParallel: '启用智能并行 / Enable', workers: '并行线数 / Workers', current: '当前 / Current',
                smartParallelHelp: '仅 HTTP/API 生效；错峰启动并放大单线间隔',
                roundInterval: '每轮检索间隔 / Round Interval', perHotelDelay: '每家酒店基础间隔 / Per-hotel Base Delay',
                requestJitter: '随机抖动 / Request Jitter', seconds: '秒 / sec', recommended120: '建议 120 秒以上 / 120+ recommended',
                reminderPolicy: '提醒策略 / Reminder Policy', repeatCount: '重复提醒次数 / Reminder Repeat Count',
                reminderCooldown: '重复提醒冷却 / Reminder Cooldown', times: '次 / Time(s)',
                notificationEvents: '推送事件 / Notification Events', repeatReminder: '重复提醒 / Repeat Reminder',
                notifyAvailable: '房源可用提醒 / Room Available', notifyUnavailable: '房源不再可用提醒 / No Longer Available',
                notifyCountChange: '可用房间数量变动提醒 / Room Count Change',
                notifyStart: '启动搜索提醒 / Start Search', notifyStop: '停止搜索提醒 / Stop Search',
                notifySearchError: '搜索异常提醒 / Search Check',
                availabilityLog: '搜索结果日志 / Search Result Log', availableSince: '空房出现时间 / Available Since',
                duration: '有效持续时间 / Duration', noLog: '暂无日志 / No log yet',
                enableBark: '启用 Bark 推送 / Enable Bark', enableServerChan: '启用 Server 酱 / Enable ServerChan',
                enableTelegram: '启用 Telegram / Enable', enableLocal: '启用本地通知 / Enable Local',
                enableEmail: '启用邮件推送 / Enable Email', localHelp: 'macOS 首次使用可能需要在 System Settings > Notifications 中允许 Terminal / Python / osascript 通知。',
                runTitle: '启动与监控 / Run Control', runSubtitle: '启动后按当前搜索范围循环检索；运行中可以停止或调整设定。',
                status: '状态 / Status', loop: '追踪轮次 / Loop', progress: '本轮进度 / Progress', uptime: '总耗时 / Uptime',
                stopped: 'STOPPED 已停止', running: 'RUNNING 运行中', progressText: '进度 / Progress',
                loopElapsed: '耗时 / Loop elapsed', currentStatus: '状态 / Current', waitingNext: '等待下一轮 / Waiting next round',
                dates: '日期 / Dates', langSummary: '语言 / Language', membershipSummary: '会员 / Membership',
                engineSummary: '引擎 / Engine', parallelSummary: '并行 / Parallel', roundSummary: '每轮间隔 / Round',
                delaySummary: '单店间隔 / Delay', available: '有房 / Available', unavailable: '无房 / Unavailable',
                check: '需确认 / Check', total: '总计 / Total', code: '编号 / Code', hotel: '酒店 / Hotel',
                minPrice: '最低价 / Min Price', left: '剩余 / Left', pushSubtitle: '显示每个推送方式是否启用，以及最近一次实时推送状态。',
                enabled: '已启用 / Enabled', disabled: '未启用 / Disabled', waiting: '等待 / Waiting',
                pushing: '推送中 / Pushing', success: '推送成功 / Success', failed: '推送失败 / Failed',
                waitingTrigger: '等待触发 / Waiting', notEnabled: '未启用 / Not enabled', noChannels: '暂无推送方式 / No channels',
                notConfigured: '未配置 / Not configured',
                telegramName: 'Telegram机器人 / Telegram Bot', localName: '本地通知 / Local Notifications',
                emailName: '邮件 / Email', barkName: 'Bark / Bark', serverChanName: 'Server酱 / Server Chan',
                tipEngine: 'HTTP/API 是默认推荐：轻量、速度快、资源占用低；当接口解析失败时会自动尝试回退 Playwright。Playwright 更接近真实浏览器，适合官网结构变化或 HTTP 失败时使用，但更重。',
                tipSmartParallel: '仅 HTTP/API 生效。会把酒店分成 1-3 条检索线并错峰启动，同时放大每条线的间隔，兼顾效率和请求节奏。默认 1 条；酒店较多时再提高到 2-3 条。',
                tipCadence: '每轮检索间隔控制两轮之间等待多久；每家酒店基础间隔控制同一检索线内访问频率；随机抖动会让间隔更自然。更稳妥的配置是每轮 120 秒以上、单店 2-5 秒并保留 30-50% 抖动。',
                tipReminder: '控制发现空房后的重复提醒。重复提醒次数为首次提醒后的追加提醒次数；最右侧 INF 表示持续提醒。冷却时间用于避免同一酒店短时间反复推送，建议 300 秒以上。',
                tipBark: '适合 iPhone/iPad。步骤：1. iPhone/iPad 安装 Bark App。2. 复制 App 首页的 Device Key。3. 填入 Bark Key。4. 公共服务保持默认 Bark Server；自建服务则填你的服务器地址。5. 勾选启用后启动搜索。',
                tipServerChan: '适合微信推送。步骤：1. 打开 Server 酱官网并用微信登录。2. 绑定微信推送通道。3. 在 SendKey 页面复制 SCT 开头的 SendKey。4. 粘贴到这里。5. 勾选启用后启动搜索。',
                tipTelegram: '步骤：1. 在 Telegram 搜索 BotFather。2. 使用 /newbot 创建机器人并复制 Bot Token。3. 给机器人发一条消息，或把机器人加入群组。4. 获取 Chat ID 后填入。5. 勾选启用后启动搜索。',
                tipLocal: '在本机弹出系统通知。步骤：1. 勾选启用本地通知。2. 点击发送测试通知。3. 如果 macOS 没弹窗，到 System Settings > Notifications 允许 Terminal / Python / osascript。4. 测试成功后启动搜索即可。',
                tipEmail: '使用 SMTP 发送邮件。步骤：1. 在邮箱后台开启 SMTP。2. 生成应用专用密码。3. 填 SMTP Host、Port、Username、Password。4. 填 From 和 To。5. 465 通常启用 SSL/TLS；587 通常也可启用 TLS。'
              },
              zh_tw: {
                appName: '東橫醬 / Toyoko Chan',
                language: '語言 / Language', runSettings: '執行設定 / Run Settings', search: '搜尋 / Search',
                searchTitle: '空房搜尋條件', searchSubtitle: '選擇日期、入住條件和飯店範圍；啟動後會自動寫入搜尋記錄。',
                tonight: '今晚 / Tonight', tomorrow: '明晚 / Tomorrow', weekend: '週末 / Weekend',
                checkin: '入住 / Check-in', checkout: '退房 / Check-out', people: '人數 / People', rooms: '房間 / Rooms',
                smoking: '吸菸 / Smoking', roomType: '房型 / Room Type', membership: '會員狀態 / Membership',
                areaPicker: '區域飯店搜尋 / Area Hotel Picker', region: '大區域 / Region', detailArea: '詳細區域 / Detail Area',
                loadHotels: '載入飯店 / Load Hotels', selectAll: '全選 / Select All', selectNone: '全不選 / Select None',
                areaHint: '選擇大區域；詳細區域可不選，預設載入整個大區域。勾選飯店後直接點 Start 搜尋。',
                areaSelected: '已選擇大區域；可直接載入全部，或選擇詳細區域。勾選飯店後直接點 Start 搜尋。',
                selectRegion: '請選擇 / Select Region', selectRegionFirst: '先選擇大區域 / Select a region first',
                filterPlaceholder: '過濾飯店主語言/英文名或編號 / Filter by primary/English hotel name or code',
                noHotels: '尚未載入飯店 / No hotels loaded yet', noMatchingHotels: '沒有符合的飯店 / No matching hotels',
                openMap: '開啟地圖 / Open Map', history: '搜尋記錄 / Search History', refresh: '重新整理 / Refresh', clear: '清空 / Clear',
                historyHint: '最多顯示最近 10 筆；完全相同設定不會重複記錄。', noHistory: '暫無搜尋記錄 / No history yet',
                searchSettings: '搜尋設定 / Search Settings', pushSettings: '推送設定 / Push Settings',
                engine: '引擎 / Engine', scanCadence: '搜尋節奏 / Scan Cadence', smartParallel: '智慧並行 / Smart Parallel',
                resultTitle: '搜尋結果 / Search Results', pushStatus: '推送狀態 / Notification Status',
                noData: '暫無結果 / No data yet', start: '啟動 / Start', stop: '停止 / Stop', defaults: '預設 / Default',
                testNotification: '傳送測試通知 / Test Notification',
                searchSettingsNote: '引擎、搜尋節奏和智慧並行集中在這裡。智慧並行僅用於 HTTP/API，並會錯峰請求。',
                pushSettingsNote: '空房、重複提醒、無房變化和啟動通知會傳送到所有已啟用通道。',
                searchEngine: '搜尋引擎 / Search Engine', engineHelp: 'HTTP/API 請求更少更快；失敗時會嘗試回退 Playwright。',
                enableSmartParallel: '啟用智慧並行 / Enable', workers: '並行線數 / Workers', current: '目前 / Current',
                smartParallelHelp: '僅 HTTP/API 生效；錯峰啟動並放大單線間隔',
                roundInterval: '每輪搜尋間隔 / Round Interval', perHotelDelay: '每家飯店基礎間隔 / Per-hotel Base Delay',
                requestJitter: '隨機抖動 / Request Jitter', seconds: '秒 / sec', recommended120: '建議 120 秒以上 / 120+ recommended',
                reminderPolicy: '提醒策略 / Reminder Policy', repeatCount: '重複提醒次數 / Reminder Repeat Count',
                reminderCooldown: '重複提醒冷卻 / Reminder Cooldown', times: '次 / Time(s)',
                notificationEvents: '推送事件 / Notification Events', repeatReminder: '重複提醒 / Repeat Reminder',
                notifyAvailable: '空房可用提醒 / Room Available', notifyUnavailable: '房源不再可用提醒 / No Longer Available',
                notifyCountChange: '可用房間數量變動提醒 / Room Count Change',
                notifyStart: '啟動搜尋提醒 / Start Search', notifyStop: '停止搜尋提醒 / Stop Search',
                notifySearchError: '搜尋異常提醒 / Search Check',
                availabilityLog: '搜尋結果日誌 / Search Result Log', availableSince: '空房出現時間 / Available Since',
                duration: '有效持續時間 / Duration', noLog: '暫無日誌 / No log yet',
                enableBark: '啟用 Bark 推送 / Enable Bark', enableServerChan: '啟用 ServerChan / Enable ServerChan',
                enableTelegram: '啟用 Telegram / Enable', enableLocal: '啟用本地通知 / Enable Local',
                enableEmail: '啟用郵件推送 / Enable Email', localHelp: 'macOS 首次使用可能需要在 System Settings > Notifications 中允許 Terminal / Python / osascript 通知。',
                runTitle: '啟動與監控 / Run Control', runSubtitle: '啟動後依目前搜尋範圍循環搜尋；執行中可以停止或調整設定。',
                status: '狀態 / Status', loop: '追蹤輪次 / Loop', progress: '本輪進度 / Progress', uptime: '總耗時 / Uptime',
                stopped: 'STOPPED 已停止', running: 'RUNNING 執行中', progressText: '進度 / Progress',
                loopElapsed: '耗時 / Loop elapsed', currentStatus: '狀態 / Current', waitingNext: '等待下一輪 / Waiting next round',
                dates: '日期 / Dates', langSummary: '語言 / Language', membershipSummary: '會員 / Membership',
                engineSummary: '引擎 / Engine', parallelSummary: '並行 / Parallel', roundSummary: '每輪間隔 / Round',
                delaySummary: '單店間隔 / Delay', available: '有房 / Available', unavailable: '無房 / Unavailable',
                check: '需確認 / Check', total: '總計 / Total', code: '編號 / Code', hotel: '飯店 / Hotel',
                minPrice: '最低價 / Min Price', left: '剩餘 / Left', pushSubtitle: '顯示每個推送方式是否啟用，以及最近一次即時推送狀態。',
                enabled: '已啟用 / Enabled', disabled: '未啟用 / Disabled', waiting: '等待 / Waiting',
                pushing: '推送中 / Pushing', success: '推送成功 / Success', failed: '推送失敗 / Failed',
                waitingTrigger: '等待觸發 / Waiting', notEnabled: '未啟用 / Not enabled', noChannels: '暫無推送方式 / No channels',
                notConfigured: '未配置 / Not configured',
                telegramName: 'Telegram機器人 / Telegram Bot', localName: '本地通知 / Local Notifications',
                emailName: '郵件 / Email', barkName: 'Bark / Bark', serverChanName: 'ServerChan / Server Chan',
                tipEngine: 'HTTP/API 是預設推薦：輕量、速度快、資源占用低；介面解析失敗時會嘗試回退 Playwright。Playwright 更接近真實瀏覽器，但更重。',
                tipSmartParallel: '僅 HTTP/API 生效。會把飯店分成 1-3 條搜尋線並錯峰啟動，同時放大每條線的間隔。預設 1 條；飯店較多時再提高到 2-3 條。',
                tipCadence: '每輪搜尋間隔控制兩輪之間等待多久；每家飯店基礎間隔控制同一搜尋線內訪問頻率；隨機抖動會讓間隔更自然。',
                tipReminder: '控制發現空房後的重複提醒。重複提醒次數為首次提醒後的追加提醒次數；最右側 INF 表示持續提醒。冷卻時間建議 300 秒以上。',
                tipBark: '適合 iPhone/iPad。步驟：1. 安裝 Bark App。2. 複製 Device Key。3. 填入 Bark Key。4. 公共服務保持預設 Bark Server；自建服務則填你的伺服器地址。',
                tipServerChan: '適合微信推送。步驟：1. 打開 ServerChan 官網並登入。2. 綁定微信推送通道。3. 複製 SendKey。4. 貼到這裡。5. 勾選啟用後啟動搜尋。',
                tipTelegram: '步驟：1. 在 Telegram 搜尋 BotFather。2. 使用 /newbot 建立機器人並複製 Bot Token。3. 給機器人發訊息或加入群組。4. 取得 Chat ID 後填入。',
                tipLocal: '在本機彈出系統通知。步驟：1. 勾選啟用本地通知。2. 點擊傳送測試通知。3. macOS 沒彈窗時，到 System Settings > Notifications 允許 Terminal / Python / osascript。',
                tipEmail: '使用 SMTP 傳送郵件。步驟：1. 在信箱後台開啟 SMTP。2. 產生應用程式密碼。3. 填 SMTP Host、Port、Username、Password。4. 填 From 和 To。'
              },
              ja: {
                appName: '東横ちゃん / Toyoko Chan',
                language: '言語 / Language', runSettings: '実行設定 / Run Settings', search: '検索 / Search',
                searchTitle: '空室検索条件', searchSubtitle: '日付、宿泊条件、ホテル範囲を選択します。開始後、検索履歴に自動保存されます。',
                tonight: '今夜 / Tonight', tomorrow: '明日の夜 / Tomorrow', weekend: '週末 / Weekend',
                checkin: 'チェックイン / Check-in', checkout: 'チェックアウト / Check-out', people: '人数 / People', rooms: '部屋数 / Rooms',
                smoking: '喫煙条件 / Smoking', roomType: '部屋タイプ / Room Type', membership: '会員状態 / Membership',
                areaPicker: 'エリア別ホテル検索 / Area Hotel Picker', region: '大エリア / Region', detailArea: '詳細エリア / Detail Area',
                loadHotels: 'ホテル読込 / Load Hotels', selectAll: 'すべて選択 / Select All', selectNone: 'すべて解除 / Select None',
                areaHint: '大エリアを選択してください。詳細エリアは任意です。ホテルを選んで Start を押すと検索します。',
                areaSelected: '大エリアを選択済みです。全体を読み込むか、詳細エリアを選択できます。',
                selectRegion: '選択してください / Select Region', selectRegionFirst: '先に大エリアを選択 / Select a region first',
                filterPlaceholder: '主言語/英語のホテル名または番号で絞り込み / Filter by primary/English hotel name or code',
                noHotels: 'ホテル未読込 / No hotels loaded yet', noMatchingHotels: '一致するホテルなし / No matching hotels',
                openMap: '地図を開く / Open Map', history: '検索履歴 / Search History', refresh: '更新 / Refresh', clear: 'クリア / Clear',
                historyHint: '直近 10 件まで表示。同一設定は重複保存されません。', noHistory: '履歴なし / No history yet',
                searchSettings: '検索設定 / Search Settings', pushSettings: '通知設定 / Push Settings',
                engine: 'エンジン / Engine', scanCadence: '検索間隔 / Scan Cadence', smartParallel: 'スマート並列 / Smart Parallel',
                resultTitle: '検索結果 / Search Results', pushStatus: '通知状態 / Notification Status',
                noData: 'データなし / No data yet', start: '開始 / Start', stop: '停止 / Stop', defaults: '初期値 / Default',
                testNotification: 'テスト通知 / Test Notification',
                searchSettingsNote: 'エンジン、検索間隔、スマート並列をここで設定します。スマート並列は HTTP/API のみ有効です。',
                pushSettingsNote: '空室、繰り返し通知、満室化、開始通知は有効なすべての通知先へ送信されます。',
                searchEngine: '検索エンジン / Search Engine', engineHelp: 'HTTP/API は軽く高速です。失敗時は Playwright へフォールバックします。',
                enableSmartParallel: 'スマート並列を有効化 / Enable', workers: '並列数 / Workers', current: '現在 / Current',
                smartParallelHelp: 'HTTP/API のみ有効；開始をずらして単線間隔を広げます',
                roundInterval: '各ラウンド間隔 / Round Interval', perHotelDelay: 'ホテルごとの基本間隔 / Per-hotel Base Delay',
                requestJitter: 'ランダム揺らぎ / Request Jitter', seconds: '秒 / sec', recommended120: '120 秒以上推奨 / 120+ recommended',
                reminderPolicy: '通知ポリシー / Reminder Policy', repeatCount: '繰り返し通知回数 / Reminder Repeat Count',
                reminderCooldown: '繰り返し通知クールダウン / Reminder Cooldown', times: '回 / Time(s)',
                notificationEvents: '通知イベント / Notification Events', repeatReminder: '繰り返し通知 / Repeat Reminder',
                notifyAvailable: '空室あり通知 / Room Available', notifyUnavailable: '空室なしに変化 / No Longer Available',
                notifyCountChange: '空室数変更通知 / Room Count Change',
                notifyStart: '検索開始通知 / Start Search', notifyStop: '検索停止通知 / Stop Search',
                notifySearchError: '検索確認通知 / Search Check',
                availabilityLog: '検索結果ログ / Search Result Log', availableSince: '空室発見時刻 / Available Since',
                duration: '有効継続時間 / Duration', noLog: 'ログなし / No log yet',
                enableBark: 'Bark 通知を有効化 / Enable Bark', enableServerChan: 'ServerChan を有効化 / Enable ServerChan',
                enableTelegram: 'Telegram を有効化 / Enable', enableLocal: 'ローカル通知を有効化 / Enable Local',
                enableEmail: 'メール通知を有効化 / Enable Email', localHelp: 'macOS では System Settings > Notifications で Terminal / Python / osascript の通知許可が必要な場合があります。',
                runTitle: '開始と監視 / Run Control', runSubtitle: '現在の検索範囲で繰り返し検索します。実行中も停止や設定変更ができます。',
                status: '状態 / Status', loop: '巡回回数 / Loop', progress: '今回の進捗 / Progress', uptime: '総稼働時間 / Uptime',
                stopped: 'STOPPED 停止中', running: 'RUNNING 実行中', progressText: '進捗 / Progress',
                loopElapsed: '経過時間 / Loop elapsed', currentStatus: '状態 / Current', waitingNext: '次回待機中 / Waiting next round',
                dates: '日付 / Dates', langSummary: '言語 / Language', membershipSummary: '会員 / Membership',
                engineSummary: 'エンジン / Engine', parallelSummary: '並列 / Parallel', roundSummary: 'ラウンド間隔 / Round',
                delaySummary: '単店間隔 / Delay', available: '空室あり / Available', unavailable: '空室なし / Unavailable',
                check: '要確認 / Check', total: '合計 / Total', code: '番号 / Code', hotel: 'ホテル / Hotel',
                minPrice: '最低価格 / Min Price', left: '残数 / Left', pushSubtitle: '各通知先の有効状態と直近の送信状態を表示します。',
                enabled: '有効 / Enabled', disabled: '無効 / Disabled', waiting: '待機 / Waiting',
                pushing: '送信中 / Pushing', success: '送信成功 / Success', failed: '送信失敗 / Failed',
                waitingTrigger: '待機中 / Waiting', notEnabled: '無効 / Not enabled', noChannels: '通知先なし / No channels',
                notConfigured: '未設定 / Not configured',
                telegramName: 'Telegramボット / Telegram Bot', localName: 'ローカル通知 / Local Notifications',
                emailName: 'メール / Email', barkName: 'Bark / Bark', serverChanName: 'ServerChan / Server Chan',
                tipEngine: 'HTTP/API を推奨します。軽量で高速、リソース消費も少なめです。解析に失敗した場合は Playwright にフォールバックします。Playwright は実ブラウザに近いですが重くなります。',
                tipSmartParallel: 'HTTP/API のみ有効です。ホテルを 1-3 本の検索ラインに分け、開始タイミングをずらし、各ラインの間隔を広げます。初期値は 1 本です。',
                tipCadence: 'ラウンド間隔は次の検索までの待ち時間です。ホテルごとの基本間隔は同じライン内のアクセス頻度です。ランダム揺らぎで間隔を自然にします。',
                tipReminder: '空室発見後の繰り返し通知を制御します。回数は初回通知後の追加通知回数です。右端の INF は継続通知を意味します。クールダウンは 300 秒以上を推奨します。',
                tipBark: 'iPhone/iPad 向けです。手順：1. Bark App をインストール。2. Device Key をコピー。3. Bark Key に入力。4. 公開サービスは既定の Bark Server、自前サーバーはその URL を入力。',
                tipServerChan: 'WeChat 通知向けです。手順：1. ServerChan にログイン。2. 通知チャンネルを連携。3. SendKey をコピー。4. ここに貼り付け。5. 有効化して検索開始。',
                tipTelegram: '手順：1. Telegram で BotFather を検索。2. /newbot でボットを作成し Bot Token をコピー。3. ボットへメッセージを送るかグループに追加。4. Chat ID を入力。',
                tipLocal: 'この Mac にシステム通知を表示します。手順：1. ローカル通知を有効化。2. テスト通知を送信。3. 表示されない場合は System Settings > Notifications で Terminal / Python / osascript を許可。',
                tipEmail: 'SMTP でメールを送信します。手順：1. メール側で SMTP を有効化。2. アプリパスワードを作成。3. SMTP Host、Port、Username、Password を入力。4. From と To を入力。'
              },
              ko: {
                appName: '토요코짱 / Toyoko Chan',
                language: '언어 / Language', runSettings: '실행 설정 / Run Settings', search: '검색 / Search',
                searchTitle: '빈 객실 검색 조건', searchSubtitle: '날짜, 숙박 조건, 호텔 범위를 선택합니다. 시작 후 검색 기록에 자동 저장됩니다.',
                tonight: '오늘 밤 / Tonight', tomorrow: '내일 밤 / Tomorrow', weekend: '주말 / Weekend',
                checkin: '체크인 / Check-in', checkout: '체크아웃 / Check-out', people: '인원 / People', rooms: '객실 / Rooms',
                smoking: '흡연 조건 / Smoking', roomType: '객실 타입 / Room Type', membership: '회원 상태 / Membership',
                areaPicker: '지역 호텔 검색 / Area Hotel Picker', region: '대지역 / Region', detailArea: '상세 지역 / Detail Area',
                loadHotels: '호텔 불러오기 / Load Hotels', selectAll: '전체 선택 / Select All', selectNone: '전체 해제 / Select None',
                areaHint: '대지역을 선택하세요. 상세 지역은 선택하지 않아도 됩니다. 호텔을 선택한 뒤 Start를 누르면 검색합니다.',
                areaSelected: '대지역이 선택되었습니다. 전체를 불러오거나 상세 지역을 선택할 수 있습니다.',
                selectRegion: '선택하세요 / Select Region', selectRegionFirst: '먼저 대지역 선택 / Select a region first',
                filterPlaceholder: '주 언어/영어 호텔명 또는 번호로 필터 / Filter by primary/English hotel name or code',
                noHotels: '호텔을 아직 불러오지 않음 / No hotels loaded yet', noMatchingHotels: '일치하는 호텔 없음 / No matching hotels',
                openMap: '지도 열기 / Open Map', history: '검색 기록 / Search History', refresh: '새로고침 / Refresh', clear: '비우기 / Clear',
                historyHint: '최근 10개까지 표시합니다. 완전히 같은 설정은 중복 저장되지 않습니다.', noHistory: '검색 기록 없음 / No history yet',
                searchSettings: '검색 설정 / Search Settings', pushSettings: '푸시 설정 / Push Settings',
                engine: '엔진 / Engine', scanCadence: '검색 주기 / Scan Cadence', smartParallel: '스마트 병렬 / Smart Parallel',
                resultTitle: '검색 결과 / Search Results', pushStatus: '푸시 상태 / Notification Status',
                noData: '결과 없음 / No data yet', start: '시작 / Start', stop: '중지 / Stop', defaults: '기본값 / Default',
                testNotification: '테스트 알림 / Test Notification',
                searchSettingsNote: '엔진, 검색 주기, 스마트 병렬을 여기에서 설정합니다. 스마트 병렬은 HTTP/API에서만 작동합니다.',
                pushSettingsNote: '빈 객실, 반복 알림, 매진 변화, 시작 알림은 활성화된 모든 채널로 전송됩니다.',
                searchEngine: '검색 엔진 / Search Engine', engineHelp: 'HTTP/API는 더 가볍고 빠릅니다. 실패하면 Playwright로 폴백합니다.',
                enableSmartParallel: '스마트 병렬 활성화 / Enable', workers: '병렬 라인 수 / Workers', current: '현재 / Current',
                smartParallelHelp: 'HTTP/API에서만 작동；시작을 분산하고 단일 라인 간격을 늘립니다',
                roundInterval: '라운드 간격 / Round Interval', perHotelDelay: '호텔별 기본 간격 / Per-hotel Base Delay',
                requestJitter: '랜덤 지터 / Request Jitter', seconds: '초 / sec', recommended120: '120초 이상 권장 / 120+ recommended',
                reminderPolicy: '알림 정책 / Reminder Policy', repeatCount: '반복 알림 횟수 / Reminder Repeat Count',
                reminderCooldown: '반복 알림 쿨다운 / Reminder Cooldown', times: '회 / Time(s)',
                notificationEvents: '푸시 이벤트 / Notification Events', repeatReminder: '반복 알림 / Repeat Reminder',
                notifyAvailable: '객실 있음 알림 / Room Available', notifyUnavailable: '객실 없음 전환 알림 / No Longer Available',
                notifyCountChange: '이용 가능 객실 수 변경 알림 / Room Count Change',
                notifyStart: '검색 시작 알림 / Start Search', notifyStop: '검색 중지 알림 / Stop Search',
                notifySearchError: '검색 확인 알림 / Search Check',
                availabilityLog: '검색 결과 로그 / Search Result Log', availableSince: '객실 발생 시간 / Available Since',
                duration: '유효 지속 시간 / Duration', noLog: '로그 없음 / No log yet',
                enableBark: 'Bark 푸시 활성화 / Enable Bark', enableServerChan: 'ServerChan 활성화 / Enable ServerChan',
                enableTelegram: 'Telegram 활성화 / Enable', enableLocal: '로컬 알림 활성화 / Enable Local',
                enableEmail: '이메일 푸시 활성화 / Enable Email', localHelp: 'macOS에서는 System Settings > Notifications에서 Terminal / Python / osascript 알림 허용이 필요할 수 있습니다.',
                runTitle: '시작 및 모니터링 / Run Control', runSubtitle: '현재 검색 범위로 반복 검색합니다. 실행 중에도 중지하거나 설정을 조정할 수 있습니다.',
                status: '상태 / Status', loop: '추적 회차 / Loop', progress: '이번 진행률 / Progress', uptime: '총 실행 시간 / Uptime',
                stopped: 'STOPPED 중지됨', running: 'RUNNING 실행 중', progressText: '진행률 / Progress',
                loopElapsed: '소요 시간 / Loop elapsed', currentStatus: '상태 / Current', waitingNext: '다음 라운드 대기 / Waiting next round',
                dates: '날짜 / Dates', langSummary: '언어 / Language', membershipSummary: '회원 / Membership',
                engineSummary: '엔진 / Engine', parallelSummary: '병렬 / Parallel', roundSummary: '라운드 간격 / Round',
                delaySummary: '호텔 간격 / Delay', available: '객실 있음 / Available', unavailable: '객실 없음 / Unavailable',
                check: '확인 필요 / Check', total: '합계 / Total', code: '번호 / Code', hotel: '호텔 / Hotel',
                minPrice: '최저가 / Min Price', left: '잔여 / Left', pushSubtitle: '각 푸시 채널의 활성화 여부와 최근 전송 상태를 표시합니다.',
                enabled: '활성화 / Enabled', disabled: '비활성화 / Disabled', waiting: '대기 / Waiting',
                pushing: '전송 중 / Pushing', success: '전송 성공 / Success', failed: '전송 실패 / Failed',
                waitingTrigger: '대기 중 / Waiting', notEnabled: '비활성화 / Not enabled', noChannels: '푸시 채널 없음 / No channels',
                notConfigured: '미설정 / Not configured',
                telegramName: 'Telegram 봇 / Telegram Bot', localName: '로컬 알림 / Local Notifications',
                emailName: '이메일 / Email', barkName: 'Bark / Bark', serverChanName: 'ServerChan / Server Chan',
                tipEngine: 'HTTP/API를 권장합니다. 가볍고 빠르며 리소스 사용이 적습니다. 분석에 실패하면 Playwright로 폴백합니다. Playwright는 실제 브라우저에 가깝지만 더 무겁습니다.',
                tipSmartParallel: 'HTTP/API에서만 작동합니다. 호텔을 1-3개 검색 라인으로 나누고 시작 시점을 분산하며 각 라인의 간격을 늘립니다. 기본값은 1개입니다.',
                tipCadence: '라운드 간격은 다음 검색까지의 대기 시간입니다. 호텔별 기본 간격은 같은 라인 안의 접근 빈도입니다. 랜덤 지터로 간격을 더 자연스럽게 만듭니다.',
                tipReminder: '빈 객실 발견 후 반복 알림을 제어합니다. 횟수는 첫 알림 이후 추가 알림 횟수입니다. 오른쪽 INF는 계속 알림을 의미합니다. 쿨다운은 300초 이상을 권장합니다.',
                tipBark: 'iPhone/iPad용입니다. 단계: 1. Bark App 설치. 2. Device Key 복사. 3. Bark Key 입력. 4. 공용 서비스는 기본 Bark Server 유지, 자체 서버는 해당 URL 입력.',
                tipServerChan: 'WeChat 푸시용입니다. 단계: 1. ServerChan 로그인. 2. 푸시 채널 연결. 3. SendKey 복사. 4. 여기에 붙여넣기. 5. 활성화 후 검색 시작.',
                tipTelegram: '단계: 1. Telegram에서 BotFather 검색. 2. /newbot으로 봇 생성 후 Bot Token 복사. 3. 봇에 메시지를 보내거나 그룹에 추가. 4. Chat ID 입력.',
                tipLocal: '이 Mac에 시스템 알림을 표시합니다. 단계: 1. 로컬 알림 활성화. 2. 테스트 알림 전송. 3. 표시되지 않으면 System Settings > Notifications에서 Terminal / Python / osascript 허용.',
                tipEmail: 'SMTP로 이메일을 보냅니다. 단계: 1. 메일 서비스에서 SMTP 활성화. 2. 앱 비밀번호 생성. 3. SMTP Host, Port, Username, Password 입력. 4. From과 To 입력.'
              }
            };
            const UI18N_EXTRA = {
              zh_cn: {
                areaMode: '区域模式 / Area', radiusMode: '方圆模式 / Radius',
                placeAddressCoordinates: '地名地址或者坐标 / Place, Address, or Coordinates',
                radius: '方圆半径 / Radius', loadNearby: '查找附近酒店 / Load Nearby',
                radiusHelp: '地址会优先通过 OpenStreetMap/Nominatim 解析；坐标可直接本地解析。 / Addresses use OpenStreetMap/Nominatim first; coordinates are parsed locally.',
                selectedHotelMap: '已选酒店地图 / Selected Hotel Map',
                selectedHotelMapHint: '地图会显示当前已勾选且带坐标的酒店。 / The map shows checked hotels that have coordinates.',
                noSelectedHotelCoords: '已选酒店没有坐标。 / Selected hotels do not have coordinates.',
                mapLibraryMissing: '地图组件未加载，请检查网络。 / Map library not loaded; please check network.',
                showingSelectedHotels: '地图显示 {count} 家已选酒店 / Showing {count} selected hotels on map.',
                radiusModeStatus: '输入地名地址或坐标与半径后加载附近酒店。 / Enter a place, address, or coordinates and radius.',
                areaIndexFailed: '区域索引加载失败 / Area index failed: ',
                loadingHotels: '正在加载酒店 / Loading hotels...',
                loadedHotels: '已加载 {count} 家酒店 / Loaded {count} hotels.',
                loadedHotelsCenter: '已加载 {count} 家酒店 / Loaded {count} hotels. Center: {center}',
                hotelLoadingFailed: '酒店加载失败 / Hotel loading failed: ',
                addressRequired: '请输入地名地址或者坐标。 / Please enter a place, address, or coordinates.',
                filteringByCoords: '正在使用坐标筛选酒店坐标缓存... / Filtering hotels by coordinates...',
                geocodingAddress: '正在通过 OpenStreetMap/Nominatim 解析地址并加载附近酒店... / Geocoding address and loading nearby hotels...',
                radiusSearchFailed: '方圆检索失败 / Radius search failed: ',
                loadedHistory: '已调用搜索记录 / Loaded history: {count} hotels.',
                restoredHotels: '已恢复上次搜索酒店列表 / Restored {count} hotels from last run.',
                selectHotelsFirst: '请先在区域酒店搜索中加载并勾选酒店。 / Please load and select hotels in Area Hotel Picker first.',
                useHistory: '调用 / Use', guestUnit: '人 / guest', roomUnit: '房 / room',
                official: '官网 / Official',
                barkTitle: 'Bark / Bark', serverChanTitle: 'Server酱 / Server Chan',
                telegramTitle: 'Telegram机器人 / Telegram Bot', localTitle: '本地通知 / Local Notifications', emailTitle: '邮件 / Email',
                barkKey: 'Bark Key / Bark Key', barkServer: 'Bark Server / Bark Server',
                criticalAlert: 'Critical Alert / Critical Alert', criticalHelp: 'Critical Alert 会忽略静音和勿扰模式；启用后会把房源信息作为 Critical Alert 发送一次。 / Critical Alert ignores Silent and DND modes and sends the room alert once.',
                criticalVolume: 'Critical Alert 音量 / Critical Alert Volume', criticalSound: 'Critical Alert 声音 / Critical Alert Sound',
                criticalSoundHelp: 'Critical Alert 默认使用 alarm。请确认 iOS Settings > Notifications > Bark 已允许 Critical Alerts 和 Sounds。 / Default sound is alarm. Make sure iOS allows Critical Alerts and Sounds for Bark.',
                testBark: '发送 Bark 测试 / Test Bark', applySound: '应用/测试声音 / Apply Sound',
                sendKey: 'SendKey / SendKey', botToken: 'Bot Token / Bot Token', chatId: 'Chat ID / Chat ID',
                smtpHost: 'SMTP Host / SMTP Host', smtpPort: 'SMTP Port / SMTP Port',
                useSslTls: '使用 SSL/TLS / Use SSL/TLS', smtpUsername: 'SMTP Username / SMTP Username',
                smtpPassword: 'SMTP Password / SMTP Password', emailFrom: '发件人 / From', emailTo: '收件人 / To',
                barkKeyTooLong: 'Bark Key 太长：请填写 Bark 首页的 Device Key，例如 N8yRQfPsATtXrqo86EsqVd，不是 Device Token。 / Bark Key is too long: use the Device Key from the Bark home screen, not the Device Token.',
                barkKeyTooShort: 'Bark Key 太短，请检查 Bark 首页的 Device Key。 / Bark Key is too short.',
                startedMessage: '已启动 / Started.', restartedMessage: '已重启 / Restarted.',
                stoppedMessage: '已停止 / Stopped.', failedToStart: '启动失败 / Failed to start', failedToStop: '停止失败 / Failed to stop',
                testNotificationSent: '测试通知已发送。如果没看到，请检查 macOS 通知权限。 / Test notification sent. If nothing appears, check macOS notification permissions.',
                testNotificationFailed: '测试通知失败 / Test notification failed',
                barkTestSent: 'Bark 测试已发送。请查看 Bark 推送状态获取结果。 / Bark test sent. Check Bark push status for the result.',
                barkTestFailed: 'Bark 测试失败 / Bark test failed',
                barkSoundSent: 'Bark Critical Alert 声音测试已发送：{sound} / Bark Critical Alert sound test sent: {sound}.',
                barkSoundFailed: 'Bark 声音测试失败 / Bark sound test failed',
                updateAvailableTitle: '发现新版本 / Update available', updateAvailableMessage: '当前 / Current: v{current} · 最新 / Latest: v{latest}',
                updateButton: '升级 / Update', upgradingTitle: '正在升级 / Upgrading',
                upgradingMessage: '正在后台执行 pip install --upgrade toyoko-tracker / Running pip install --upgrade toyoko-tracker in the background',
                updatingButton: '升级中 / Updating', upgradedTitle: '升级完成 / Update finished',
                upgradedMessage: '请重启程序以使用新版本 / Please restart the app to use the new version.',
                currentAction: '状态 / Current', memberPrice: '会员价 / Member', memberPriceUnknown: '会员价未知 / Member price unknown',
                nonMemberPrice: '非会员价 / Non-member', sentOk: '发送成功 / sent OK',
                terminalNotifierSentOk: 'terminal-notifier 发送成功 / terminal-notifier sent OK',
                osascriptSentOk: 'osascript 发送成功 / osascript sent OK'
              },
              zh_tw: {
                areaMode: '區域模式 / Area', radiusMode: '方圓模式 / Radius',
                placeAddressCoordinates: '地名地址或者座標 / Place, Address, or Coordinates',
                radius: '方圓半徑 / Radius', loadNearby: '查找附近飯店 / Load Nearby',
                radiusHelp: '地址會優先透過 OpenStreetMap/Nominatim 解析；座標可直接本地解析。 / Addresses use OpenStreetMap/Nominatim first; coordinates are parsed locally.',
                selectedHotelMap: '已選飯店地圖 / Selected Hotel Map',
                selectedHotelMapHint: '地圖會顯示目前已勾選且帶座標的飯店。 / The map shows checked hotels that have coordinates.',
                noSelectedHotelCoords: '已選飯店沒有座標。 / Selected hotels do not have coordinates.',
                mapLibraryMissing: '地圖元件未載入，請檢查網路。 / Map library not loaded; please check network.',
                showingSelectedHotels: '地圖顯示 {count} 家已選飯店 / Showing {count} selected hotels on map.',
                radiusModeStatus: '輸入地名地址或座標與半徑後載入附近飯店。 / Enter a place, address, or coordinates and radius.',
                areaIndexFailed: '區域索引載入失敗 / Area index failed: ',
                loadingHotels: '正在載入飯店 / Loading hotels...',
                loadedHotels: '已載入 {count} 家飯店 / Loaded {count} hotels.',
                loadedHotelsCenter: '已載入 {count} 家飯店 / Loaded {count} hotels. Center: {center}',
                hotelLoadingFailed: '飯店載入失敗 / Hotel loading failed: ',
                addressRequired: '請輸入地名地址或者座標。 / Please enter a place, address, or coordinates.',
                filteringByCoords: '正在使用座標篩選飯店座標快取... / Filtering hotels by coordinates...',
                geocodingAddress: '正在透過 OpenStreetMap/Nominatim 解析地址並載入附近飯店... / Geocoding address and loading nearby hotels...',
                radiusSearchFailed: '方圓搜尋失敗 / Radius search failed: ',
                loadedHistory: '已套用搜尋記錄 / Loaded history: {count} hotels.',
                restoredHotels: '已還原上次搜尋飯店列表 / Restored {count} hotels from last run.',
                selectHotelsFirst: '請先在區域飯店搜尋中載入並勾選飯店。 / Please load and select hotels in Area Hotel Picker first.',
                useHistory: '調用 / Use', guestUnit: '人 / guest', roomUnit: '房 / room',
                official: '官網 / Official',
                barkTitle: 'Bark / Bark', serverChanTitle: 'ServerChan / Server Chan',
                telegramTitle: 'Telegram機器人 / Telegram Bot', localTitle: '本地通知 / Local Notifications', emailTitle: '郵件 / Email',
                barkKey: 'Bark Key / Bark Key', barkServer: 'Bark Server / Bark Server',
                criticalAlert: 'Critical Alert / Critical Alert', criticalHelp: 'Critical Alert 會忽略靜音和勿擾模式；啟用後會把房源資訊作為 Critical Alert 傳送一次。 / Critical Alert ignores Silent and DND modes and sends the room alert once.',
                criticalVolume: 'Critical Alert 音量 / Critical Alert Volume', criticalSound: 'Critical Alert 聲音 / Critical Alert Sound',
                criticalSoundHelp: 'Critical Alert 預設使用 alarm。請確認 iOS Settings > Notifications > Bark 已允許 Critical Alerts 和 Sounds。 / Default sound is alarm. Make sure iOS allows Critical Alerts and Sounds for Bark.',
                testBark: '傳送 Bark 測試 / Test Bark', applySound: '套用/測試聲音 / Apply Sound',
                sendKey: 'SendKey / SendKey', botToken: 'Bot Token / Bot Token', chatId: 'Chat ID / Chat ID',
                smtpHost: 'SMTP Host / SMTP Host', smtpPort: 'SMTP Port / SMTP Port',
                useSslTls: '使用 SSL/TLS / Use SSL/TLS', smtpUsername: 'SMTP Username / SMTP Username',
                smtpPassword: 'SMTP Password / SMTP Password', emailFrom: '寄件人 / From', emailTo: '收件人 / To',
                barkKeyTooLong: 'Bark Key 太長：請填寫 Bark 首頁的 Device Key，例如 N8yRQfPsATtXrqo86EsqVd，不是 Device Token。 / Bark Key is too long: use the Device Key from the Bark home screen, not the Device Token.',
                barkKeyTooShort: 'Bark Key 太短，請檢查 Bark 首頁的 Device Key。 / Bark Key is too short.',
                startedMessage: '已啟動 / Started.', restartedMessage: '已重啟 / Restarted.',
                stoppedMessage: '已停止 / Stopped.', failedToStart: '啟動失敗 / Failed to start', failedToStop: '停止失敗 / Failed to stop',
                testNotificationSent: '測試通知已傳送。如果沒看到，請檢查 macOS 通知權限。 / Test notification sent. If nothing appears, check macOS notification permissions.',
                testNotificationFailed: '測試通知失敗 / Test notification failed',
                barkTestSent: 'Bark 測試已傳送。請查看 Bark 推送狀態取得結果。 / Bark test sent. Check Bark push status for the result.',
                barkTestFailed: 'Bark 測試失敗 / Bark test failed',
                barkSoundSent: 'Bark Critical Alert 聲音測試已傳送：{sound} / Bark Critical Alert sound test sent: {sound}.',
                barkSoundFailed: 'Bark 聲音測試失敗 / Bark sound test failed',
                updateAvailableTitle: '發現新版本 / Update available', updateAvailableMessage: '目前 / Current: v{current} · 最新 / Latest: v{latest}',
                updateButton: '升級 / Update', upgradingTitle: '正在升級 / Upgrading',
                upgradingMessage: '正在背景執行 pip install --upgrade toyoko-tracker / Running pip install --upgrade toyoko-tracker in the background',
                updatingButton: '升級中 / Updating', upgradedTitle: '升級完成 / Update finished',
                upgradedMessage: '請重啟程式以使用新版本 / Please restart the app to use the new version.',
                currentAction: '狀態 / Current', memberPrice: '會員價 / Member', memberPriceUnknown: '會員價未知 / Member price unknown',
                nonMemberPrice: '非會員價 / Non-member', sentOk: '傳送成功 / sent OK',
                terminalNotifierSentOk: 'terminal-notifier 傳送成功 / terminal-notifier sent OK',
                osascriptSentOk: 'osascript 傳送成功 / osascript sent OK'
              },
              ja: {
                areaMode: 'エリアモード / Area', radiusMode: '半径モード / Radius',
                placeAddressCoordinates: '地名・住所または座標 / Place, Address, or Coordinates',
                radius: '半径 / Radius', loadNearby: '周辺ホテルを検索 / Load Nearby',
                radiusHelp: '住所は OpenStreetMap/Nominatim で優先的に座標化します。座標はローカルで直接解析します。 / Addresses use OpenStreetMap/Nominatim first; coordinates are parsed locally.',
                selectedHotelMap: '選択ホテル地図 / Selected Hotel Map',
                selectedHotelMapHint: 'チェック済みで座標があるホテルを地図に表示します。 / The map shows checked hotels that have coordinates.',
                noSelectedHotelCoords: '選択ホテルに座標がありません。 / Selected hotels do not have coordinates.',
                mapLibraryMissing: '地図コンポーネントが読み込まれていません。ネットワークを確認してください。 / Map library not loaded; please check network.',
                showingSelectedHotels: '選択ホテル {count} 件を地図に表示 / Showing {count} selected hotels on map.',
                radiusModeStatus: '地名・住所または座標と半径を指定してホテルを読み込みます。 / Enter a place, address, or coordinates and radius.',
                areaIndexFailed: '地域一覧の読込に失敗 / Area index failed: ',
                loadingHotels: 'ホテル読込中 / Loading hotels...',
                loadedHotels: '{count} 件のホテルを読み込みました / Loaded {count} hotels.',
                loadedHotelsCenter: '{count} 件のホテルを読み込みました / Loaded {count} hotels. Center: {center}',
                hotelLoadingFailed: 'ホテル読込失敗 / Hotel loading failed: ',
                addressRequired: '地名・住所または座標を入力してください。 / Please enter a place, address, or coordinates.',
                filteringByCoords: '座標を使用してホテル座標キャッシュを確認中... / Filtering hotels by coordinates...',
                geocodingAddress: 'OpenStreetMap/Nominatim で住所を座標化し、周辺ホテルを読み込み中... / Geocoding address and loading nearby hotels...',
                radiusSearchFailed: '半径検索に失敗 / Radius search failed: ',
                loadedHistory: '履歴を読み込みました / Loaded history: {count} hotels.',
                restoredHotels: '前回のホテル一覧を復元しました / Restored {count} hotels from last run.',
                selectHotelsFirst: '先にホテルを読み込んで選択してください。 / Please load and select hotels in Area Hotel Picker first.',
                useHistory: '適用 / Use', guestUnit: '人 / guest', roomUnit: '部屋 / room',
                official: '公式 / Official',
                barkTitle: 'Bark / Bark', serverChanTitle: 'ServerChan / Server Chan',
                telegramTitle: 'Telegramボット / Telegram Bot', localTitle: 'ローカル通知 / Local Notifications', emailTitle: 'メール / Email',
                barkKey: 'Bark Key / Bark Key', barkServer: 'Bark Server / Bark Server',
                criticalAlert: 'Critical Alert / Critical Alert', criticalHelp: 'Critical Alert はサイレントとおやすみモードを無視し、空室通知を 1 回送信します。 / Critical Alert ignores Silent and DND modes and sends the room alert once.',
                criticalVolume: 'Critical Alert 音量 / Critical Alert Volume', criticalSound: 'Critical Alert サウンド / Critical Alert Sound',
                criticalSoundHelp: 'Critical Alert の既定サウンドは alarm です。iOS Settings > Notifications > Bark で Critical Alerts と Sounds を許可してください。 / Default sound is alarm. Make sure iOS allows Critical Alerts and Sounds for Bark.',
                testBark: 'Bark テスト送信 / Test Bark', applySound: 'サウンド適用/テスト / Apply Sound',
                sendKey: 'SendKey / SendKey', botToken: 'Bot Token / Bot Token', chatId: 'Chat ID / Chat ID',
                smtpHost: 'SMTP Host / SMTP Host', smtpPort: 'SMTP Port / SMTP Port',
                useSslTls: 'SSL/TLS を使用 / Use SSL/TLS', smtpUsername: 'SMTP Username / SMTP Username',
                smtpPassword: 'SMTP Password / SMTP Password', emailFrom: '送信元 / From', emailTo: '宛先 / To',
                barkKeyTooLong: 'Bark Key が長すぎます。Bark ホーム画面の Device Key を入力してください。Device Token ではありません。 / Bark Key is too long: use the Device Key from the Bark home screen, not the Device Token.',
                barkKeyTooShort: 'Bark Key が短すぎます。Bark ホーム画面の Device Key を確認してください。 / Bark Key is too short.',
                startedMessage: '開始しました / Started.', restartedMessage: '再起動しました / Restarted.',
                stoppedMessage: '停止しました / Stopped.', failedToStart: '開始に失敗 / Failed to start', failedToStop: '停止に失敗 / Failed to stop',
                testNotificationSent: 'テスト通知を送信しました。表示されない場合は macOS の通知権限を確認してください。 / Test notification sent. If nothing appears, check macOS notification permissions.',
                testNotificationFailed: 'テスト通知に失敗 / Test notification failed',
                barkTestSent: 'Bark テストを送信しました。Bark の送信状態を確認してください。 / Bark test sent. Check Bark push status for the result.',
                barkTestFailed: 'Bark テストに失敗 / Bark test failed',
                barkSoundSent: 'Bark Critical Alert サウンドテストを送信しました：{sound} / Bark Critical Alert sound test sent: {sound}.',
                barkSoundFailed: 'Bark サウンドテストに失敗 / Bark sound test failed',
                updateAvailableTitle: '新しいバージョンがあります / Update available', updateAvailableMessage: '現在 / Current: v{current} · 最新 / Latest: v{latest}',
                updateButton: '更新 / Update', upgradingTitle: '更新中 / Upgrading',
                upgradingMessage: 'バックグラウンドで pip install --upgrade toyoko-tracker を実行しています / Running pip install --upgrade toyoko-tracker in the background',
                updatingButton: '更新中 / Updating', upgradedTitle: '更新完了 / Update finished',
                upgradedMessage: '新バージョンを使用するにはアプリを再起動してください / Please restart the app to use the new version.',
                currentAction: '状態 / Current', memberPrice: '会員価格 / Member', memberPriceUnknown: '会員価格不明 / Member price unknown',
                nonMemberPrice: '非会員価格 / Non-member', sentOk: '送信成功 / sent OK',
                terminalNotifierSentOk: 'terminal-notifier 送信成功 / terminal-notifier sent OK',
                osascriptSentOk: 'osascript 送信成功 / osascript sent OK'
              },
              ko: {
                areaMode: '지역 모드 / Area', radiusMode: '반경 모드 / Radius',
                placeAddressCoordinates: '장소, 주소 또는 좌표 / Place, Address, or Coordinates',
                radius: '반경 / Radius', loadNearby: '주변 호텔 찾기 / Load Nearby',
                radiusHelp: '주소는 OpenStreetMap/Nominatim으로 먼저 좌표화하고, 좌표는 로컬에서 바로 해석합니다. / Addresses use OpenStreetMap/Nominatim first; coordinates are parsed locally.',
                selectedHotelMap: '선택 호텔 지도 / Selected Hotel Map',
                selectedHotelMapHint: '좌표가 있는 체크된 호텔을 지도에 표시합니다. / The map shows checked hotels that have coordinates.',
                noSelectedHotelCoords: '선택한 호텔에 좌표가 없습니다. / Selected hotels do not have coordinates.',
                mapLibraryMissing: '지도 구성 요소를 불러오지 못했습니다. 네트워크를 확인해 주세요. / Map library not loaded; please check network.',
                showingSelectedHotels: '선택한 호텔 {count}개를 지도에 표시 / Showing {count} selected hotels on map.',
                radiusModeStatus: '장소, 주소 또는 좌표와 반경을 입력해 호텔을 불러옵니다. / Enter a place, address, or coordinates and radius.',
                areaIndexFailed: '지역 목록 불러오기 실패 / Area index failed: ',
                loadingHotels: '호텔 불러오는 중 / Loading hotels...',
                loadedHotels: '{count}개 호텔을 불러왔습니다 / Loaded {count} hotels.',
                loadedHotelsCenter: '{count}개 호텔을 불러왔습니다 / Loaded {count} hotels. Center: {center}',
                hotelLoadingFailed: '호텔 불러오기 실패 / Hotel loading failed: ',
                addressRequired: '장소, 주소 또는 좌표를 입력해 주세요. / Please enter a place, address, or coordinates.',
                filteringByCoords: '좌표로 호텔 좌표 캐시를 확인하는 중... / Filtering hotels by coordinates...',
                geocodingAddress: 'OpenStreetMap/Nominatim으로 주소를 좌표화하고 주변 호텔을 불러오는 중... / Geocoding address and loading nearby hotels...',
                radiusSearchFailed: '반경 검색 실패 / Radius search failed: ',
                loadedHistory: '기록을 불러왔습니다 / Loaded history: {count} hotels.',
                restoredHotels: '이전 호텔 목록을 복원했습니다 / Restored {count} hotels from last run.',
                selectHotelsFirst: '먼저 호텔을 불러오고 선택해 주세요. / Please load and select hotels in Area Hotel Picker first.',
                useHistory: '적용 / Use', guestUnit: '명 / guest', roomUnit: '객실 / room',
                official: '공식 / Official',
                barkTitle: 'Bark / Bark', serverChanTitle: 'ServerChan / Server Chan',
                telegramTitle: 'Telegram 봇 / Telegram Bot', localTitle: '로컬 알림 / Local Notifications', emailTitle: '이메일 / Email',
                barkKey: 'Bark Key / Bark Key', barkServer: 'Bark Server / Bark Server',
                criticalAlert: 'Critical Alert / Critical Alert', criticalHelp: 'Critical Alert는 무음 및 방해금지 모드를 무시하고 객실 알림을 한 번 보냅니다. / Critical Alert ignores Silent and DND modes and sends the room alert once.',
                criticalVolume: 'Critical Alert 볼륨 / Critical Alert Volume', criticalSound: 'Critical Alert 소리 / Critical Alert Sound',
                criticalSoundHelp: 'Critical Alert 기본 소리는 alarm입니다. iOS Settings > Notifications > Bark에서 Critical Alerts와 Sounds를 허용해 주세요. / Default sound is alarm. Make sure iOS allows Critical Alerts and Sounds for Bark.',
                testBark: 'Bark 테스트 전송 / Test Bark', applySound: '소리 적용/테스트 / Apply Sound',
                sendKey: 'SendKey / SendKey', botToken: 'Bot Token / Bot Token', chatId: 'Chat ID / Chat ID',
                smtpHost: 'SMTP Host / SMTP Host', smtpPort: 'SMTP Port / SMTP Port',
                useSslTls: 'SSL/TLS 사용 / Use SSL/TLS', smtpUsername: 'SMTP Username / SMTP Username',
                smtpPassword: 'SMTP Password / SMTP Password', emailFrom: '보낸 사람 / From', emailTo: '받는 사람 / To',
                barkKeyTooLong: 'Bark Key가 너무 깁니다. Bark 홈 화면의 Device Key를 입력해 주세요. Device Token이 아닙니다. / Bark Key is too long: use the Device Key from the Bark home screen, not the Device Token.',
                barkKeyTooShort: 'Bark Key가 너무 짧습니다. Bark 홈 화면의 Device Key를 확인해 주세요. / Bark Key is too short.',
                startedMessage: '시작됨 / Started.', restartedMessage: '재시작됨 / Restarted.',
                stoppedMessage: '중지됨 / Stopped.', failedToStart: '시작 실패 / Failed to start', failedToStop: '중지 실패 / Failed to stop',
                testNotificationSent: '테스트 알림을 보냈습니다. 보이지 않으면 macOS 알림 권한을 확인해 주세요. / Test notification sent. If nothing appears, check macOS notification permissions.',
                testNotificationFailed: '테스트 알림 실패 / Test notification failed',
                barkTestSent: 'Bark 테스트를 보냈습니다. Bark 푸시 상태에서 결과를 확인하세요. / Bark test sent. Check Bark push status for the result.',
                barkTestFailed: 'Bark 테스트 실패 / Bark test failed',
                barkSoundSent: 'Bark Critical Alert 소리 테스트를 보냈습니다: {sound} / Bark Critical Alert sound test sent: {sound}.',
                barkSoundFailed: 'Bark 소리 테스트 실패 / Bark sound test failed',
                updateAvailableTitle: '새 버전 발견 / Update available', updateAvailableMessage: '현재 / Current: v{current} · 최신 / Latest: v{latest}',
                updateButton: '업데이트 / Update', upgradingTitle: '업데이트 중 / Upgrading',
                upgradingMessage: '백그라운드에서 pip install --upgrade toyoko-tracker 실행 중 / Running pip install --upgrade toyoko-tracker in the background',
                updatingButton: '업데이트 중 / Updating', upgradedTitle: '업데이트 완료 / Update finished',
                upgradedMessage: '새 버전을 사용하려면 앱을 다시 시작해 주세요 / Please restart the app to use the new version.',
                currentAction: '상태 / Current', memberPrice: '회원가 / Member', memberPriceUnknown: '회원가 알 수 없음 / Member price unknown',
                nonMemberPrice: '비회원가 / Non-member', sentOk: '전송 성공 / sent OK',
                terminalNotifierSentOk: 'terminal-notifier 전송 성공 / terminal-notifier sent OK',
                osascriptSentOk: 'osascript 전송 성공 / osascript sent OK'
              }
            };
            Object.keys(UI18N_EXTRA).forEach(lang => Object.assign(UI18N[lang] || {}, UI18N_EXTRA[lang]));
            const LANG_OPTION_TEXT = {
              zh_cn: {zh_cn:'中文(简体) / Simplified Chinese', zh_tw:'中文(繁体) / Traditional Chinese', ja:'日语 / Japanese', ko:'韩语 / Korean'},
              zh_tw: {zh_cn:'中文(簡體) / Simplified Chinese', zh_tw:'中文(繁體) / Traditional Chinese', ja:'日語 / Japanese', ko:'韓語 / Korean'},
              ja: {zh_cn:'中国語(簡体) / Simplified Chinese', zh_tw:'中国語(繁体) / Traditional Chinese', ja:'日本語 / Japanese', ko:'韓国語 / Korean'},
              ko: {zh_cn:'중국어(간체) / Simplified Chinese', zh_tw:'중국어(번체) / Traditional Chinese', ja:'일본어 / Japanese', ko:'한국어 / Korean'}
            };
            function currentLang(){ return document.getElementById('primary_language')?.value || 'zh_cn'; }
            function tx(key){ const lang=currentLang(); return (UI18N[lang] && UI18N[lang][key]) || UI18N.zh_cn[key] || key; }
            function fmt(key, values){
              return tx(key).replace(/\{(\w+)\}/g, (_, name) => values && values[name] != null ? String(values[name]) : '');
            }
            function setNodeText(selector, text){ const el=document.querySelector(selector); if(el) el.textContent=text; }
            function setLabelFor(id, text){ const el=document.querySelector(`label[for="${id}"]`); if(el) el.textContent=text; }
            function setPreviousLabel(id, text){
              const el = document.getElementById(id);
              const label = el?.previousElementSibling;
              if (label && label.tagName === 'LABEL') label.textContent = text;
            }
            function setSelectOptions(id, labels){
              const el=document.getElementById(id); if(!el) return;
              Array.from(el.options).forEach(opt => { if (labels[opt.value]) opt.textContent = labels[opt.value]; });
            }
            function setInlineLabel(selector, text){
              const label = document.querySelector(selector);
              if (!label) return;
              Array.from(label.childNodes).forEach(node => {
                if (node.nodeType === Node.TEXT_NODE) node.remove();
              });
              label.appendChild(document.createTextNode(' ' + text));
            }
            function setCheckboxLabel(id, text){
              const input = document.getElementById(id);
              const label = input ? input.closest('label') : null;
              if (!label) return;
              Array.from(label.childNodes).forEach(node => {
                if (node.nodeType === Node.TEXT_NODE) node.remove();
              });
              label.appendChild(document.createTextNode(' ' + text));
            }
            function setAllText(selector, values){
              document.querySelectorAll(selector).forEach((el, idx) => {
                if (values[idx] != null) el.textContent = values[idx];
              });
            }
            const AREA_PRIMARY_NAME_BY_LANG = {
              ja: {
                hokkaido:'北海道', tohoku:'東北', kanto:'関東', tokai:'東海 / 甲信越 / 北陸', kinki:'近畿', chugoku_shikoku:'中国 / 四国', kyushu_okinawa:'九州 / 沖縄',
                Hokkaido:'北海道', Aomori:'青森', Iwate:'岩手', Miyagi:'宮城', Akita:'秋田', Yamagata:'山形', Fukushima:'福島',
                Ibaraki:'茨城', Tochigi:'栃木', Gunma:'群馬', Saitama:'埼玉', Chiba:'千葉', Tokyo:'東京', Kanagawa:'神奈川',
                Niigata:'新潟', Toyama:'富山', Ishikawa:'石川', Fukui:'福井', Yamanashi:'山梨', Nagano:'長野', Gifu:'岐阜', Shizuoka:'静岡', Aichi:'愛知', Mie:'三重',
                Shiga:'滋賀', Kyoto:'京都', Osaka:'大阪', Hyogo:'兵庫', Nara:'奈良', Wakayama:'和歌山',
                Tottori:'鳥取', Shimane:'島根', Okayama:'岡山', Hiroshima:'広島', Yamaguchi:'山口', Tokushima:'徳島', Kagawa:'香川', Ehime:'愛媛', Kochi:'高知',
                Fukuoka:'福岡', Saga:'佐賀', Nagasaki:'長崎', Kumamoto:'熊本', Oita:'大分', Miyazaki:'宮崎', Kagoshima:'鹿児島', Okinawa:'沖縄'
              },
              ko: {
                hokkaido:'홋카이도', tohoku:'도호쿠', kanto:'간토', tokai:'도카이 / 고신에쓰 / 호쿠리쿠', kinki:'긴키', chugoku_shikoku:'주고쿠 / 시코쿠', kyushu_okinawa:'규슈 / 오키나와',
                Hokkaido:'홋카이도', Aomori:'아오모리', Iwate:'이와테', Miyagi:'미야기', Akita:'아키타', Yamagata:'야마가타', Fukushima:'후쿠시마',
                Ibaraki:'이바라키', Tochigi:'도치기', Gunma:'군마', Saitama:'사이타마', Chiba:'지바', Tokyo:'도쿄', Kanagawa:'가나가와',
                Niigata:'니가타', Toyama:'도야마', Ishikawa:'이시카와', Fukui:'후쿠이', Yamanashi:'야마나시', Nagano:'나가노', Gifu:'기후', Shizuoka:'시즈오카', Aichi:'아이치', Mie:'미에',
                Shiga:'시가', Kyoto:'교토', Osaka:'오사카', Hyogo:'효고', Nara:'나라', Wakayama:'와카야마',
                Tottori:'돗토리', Shimane:'시마네', Okayama:'오카야마', Hiroshima:'히로시마', Yamaguchi:'야마구치', Tokushima:'도쿠시마', Kagawa:'가가와', Ehime:'에히메', Kochi:'고치',
                Fukuoka:'후쿠오카', Saga:'사가', Nagasaki:'나가사키', Kumamoto:'구마모토', Oita:'오이타', Miyazaki:'미야자키', Kagoshima:'가고시마', Okinawa:'오키나와'
              }
            };
            function bilingualText(primary, english){
              const p = String(primary || '').trim();
              const e = String(english || '').trim();
              if (p && e && p.toLowerCase() !== e.toLowerCase()) return `${p} / ${e}`;
              return p || e;
            }
            function localizedAreaParts(item){
              if (!item) return {primary:'', en:''};
              const lang = currentLang();
              const en = item.name || '';
              if (lang === 'zh_cn' || lang === 'zh_tw') return {primary:item.label_zh || item.name_zh || '', en};
              const map = AREA_PRIMARY_NAME_BY_LANG[lang] || {};
              return {primary:map[item.key] || map[en] || '', en};
            }
            function localizedAreaLabel(item){
              const parts = localizedAreaParts(item);
              return bilingualText(parts.primary, parts.en);
            }
            function allOfLabel(primary, english){
              const lang = currentLang();
              const p = String(primary || '').trim();
              const e = String(english || p || '').trim();
              const allPrimary = lang === 'ja' ? `すべての ${p || e}` : lang === 'ko' ? `${p || e} 전체` : `全部 ${p || e}`;
              return bilingualText(allPrimary, `All of ${e}`);
            }
            function channelName(key, fallback){
              const map = {telegram:'telegramName', local:'localName', email:'emailName', bark:'barkName', serverchan:'serverChanName'};
              return map[key] ? tx(map[key]) : (fallback || key);
            }
            function historyAreaFallback(kind, value){
              const lang = currentLang();
              if (kind === 'region') {
                if (!value) return lang === 'ja' ? '地域未選択 / No region' : lang === 'ko' ? '지역 미선택 / No region' : lang === 'zh_tw' ? '未選擇區域 / No region' : '未选择区域 / No region';
                return `Region ${value}`;
              }
              if (!value) return lang === 'ja' ? 'すべての地域 / All areas' : lang === 'ko' ? '전체 지역 / All areas' : lang === 'zh_tw' ? '全部區域 / All areas' : '全部区域 / All areas';
              return value;
            }
            function applyUiLanguage(){
              const lang = currentLang();
              document.title = tx('appName');
              setNodeText('.topbar h2', tx('appName'));
              setNodeText('#footer-app-name', tx('appName'));
              setLabelFor('primary_language', tx('language'));
              setNodeText('#run_settings_legend', tx('runSettings'));
              setNodeText('#search_panel > summary', tx('search'));
              setNodeText('.search-title', tx('searchTitle'));
              setNodeText('.search-subtitle', tx('searchSubtitle'));
              setNodeText('#btn_today', tx('tonight'));
              setNodeText('#btn_tomorrow', tx('tomorrow'));
              setNodeText('#btn_weekend', tx('weekend'));
              const labels = document.querySelectorAll('.search-grid .control-box label');
              [tx('checkin'), tx('checkout'), tx('people'), tx('rooms'), tx('smoking'), tx('roomType'), tx('membership')].forEach((text, idx)=>{ if(labels[idx]) labels[idx].textContent=text; });
              const areaSummary = document.querySelector('#area_picker_panel > summary');
              if (areaSummary) areaSummary.textContent = tx('areaPicker');
              setInlineLabel('#hotel_picker_mode_tabs label:nth-child(1)', tx('areaMode'));
              setInlineLabel('#hotel_picker_mode_tabs label:nth-child(2)', tx('radiusMode'));
              const areaLabels = document.querySelectorAll('#area_mode_panel .row label');
              if (areaLabels[0]) areaLabels[0].textContent = tx('region');
              if (areaLabels[1]) areaLabels[1].textContent = tx('detailArea');
              const radiusLabels = document.querySelectorAll('#radius_mode_panel .radius-grid label');
              if (radiusLabels[0]) radiusLabels[0].textContent = tx('placeAddressCoordinates');
              if (radiusLabels[1]) radiusLabels[1].textContent = tx('radius');
              setNodeText('#btn_radius_load', tx('loadNearby'));
              const radiusHelp = document.querySelector('#radius_mode_panel .area-toolbar .help');
              if (radiusHelp) radiusHelp.textContent = tx('radiusHelp');
              setNodeText('#btn_area_load', tx('loadHotels'));
              setNodeText('#btn_area_all', tx('selectAll'));
              setNodeText('#btn_area_none', tx('selectNone'));
              setNodeText('.selected-map-title', tx('selectedHotelMap'));
              const mapStatus = document.getElementById('area_map_status');
              if (mapStatus && !(Array.isArray(AREA_HOTELS) && AREA_HOTELS.length)) mapStatus.textContent = tx('selectedHotelMapHint');
              const areaFilter = document.getElementById('area_filter');
              if (areaFilter) areaFilter.placeholder = tx('filterPlaceholder');
              const historySummary = document.querySelector('details.box:not(#area_picker_panel):not(#search_panel):not(.settings-panel) summary');
              if (historySummary) historySummary.textContent = tx('history');
              setNodeText('#btn_history_refresh', tx('refresh'));
              setNodeText('#btn_history_clear', tx('clear'));
              const historyPanel = document.getElementById('search_history')?.closest('details');
              const historyHelp = historyPanel?.querySelector('.area-toolbar .help');
              if (historyHelp) historyHelp.textContent = tx('historyHint');
              const settingsSummaries = document.querySelectorAll('details.settings-panel > summary');
              if (settingsSummaries[0]) settingsSummaries[0].textContent = tx('searchSettings');
              if (settingsSummaries[1]) settingsSummaries[1].textContent = tx('pushSettings');
              const settingsNotes = document.querySelectorAll('.settings-note');
              if (settingsNotes[0]) settingsNotes[0].textContent = tx('searchSettingsNote');
              if (settingsNotes[1]) settingsNotes[1].textContent = tx('pushSettingsNote');
              const infoTitles = document.querySelectorAll('.settings-card > h3.info-title');
              [tx('engine'), tx('smartParallel'), tx('scanCadence'), tx('reminderPolicy'), tx('barkTitle'), tx('serverChanTitle'), tx('telegramTitle'), tx('localTitle'), tx('emailTitle')].forEach((text, idx)=>{ if(infoTitles[idx]) infoTitles[idx].textContent=text; });
              ['tipEngine','tipSmartParallel','tipCadence','tipReminder','tipBark','tipServerChan','tipTelegram','tipLocal','tipEmail'].forEach((key, idx)=>{ if(infoTitles[idx]) infoTitles[idx].setAttribute('data-tip', tx(key)); });
              const engineCard = document.querySelectorAll('.settings-card')[0];
              if (engineCard) {
                const labels = engineCard.querySelectorAll('label');
                if (labels[0]) labels[0].textContent = tx('searchEngine');
                const help = engineCard.querySelector('.help');
                if (help) help.textContent = tx('engineHelp');
              }
              const smartCard = document.querySelectorAll('.settings-card')[1];
              if (smartCard) {
                const labels = smartCard.querySelectorAll('label');
                if (labels[1]) labels[1].textContent = tx('workers');
              }
              setCheckboxLabel('smart_parallel_enabled', tx('enableSmartParallel'));
              const cadenceCard = document.querySelectorAll('.settings-card')[2];
              if (cadenceCard) {
                const labels = cadenceCard.querySelectorAll('label');
                [tx('roundInterval'), tx('perHotelDelay'), tx('requestJitter')].forEach((text, idx)=>{ if(labels[idx]) labels[idx].textContent=text; });
              }
	              const reminderCard = document.querySelectorAll('.settings-card')[3];
	              if (reminderCard) {
	                const labels = reminderCard.querySelectorAll('label');
	                setNodeText('#notify_events_title', tx('notificationEvents'));
	                setNodeText('#repeat_reminder_title', tx('repeatReminder'));
	                [tx('repeatCount'), tx('reminderCooldown')].forEach((text, idx)=>{ if(labels[idx + 6]) labels[idx + 6].textContent=text; });
	              }
	              setCheckboxLabel('notify_available', tx('notifyAvailable'));
	              setCheckboxLabel('notify_unavailable', tx('notifyUnavailable'));
	              setCheckboxLabel('notify_availability_count_change', tx('notifyCountChange'));
	              setCheckboxLabel('notify_start', tx('notifyStart'));
	              setCheckboxLabel('notify_stop', tx('notifyStop'));
	              setCheckboxLabel('notify_search_error', tx('notifySearchError'));
              setCheckboxLabel('enable_bark', tx('enableBark'));
              setCheckboxLabel('bark_critical_enabled', tx('criticalAlert'));
              setCheckboxLabel('enable_serverchan', tx('enableServerChan'));
              setCheckboxLabel('enable_telegram', tx('enableTelegram'));
              setCheckboxLabel('enable_local', tx('enableLocal'));
              setCheckboxLabel('enable_email', tx('enableEmail'));
              setPreviousLabel('bark_key', tx('barkKey'));
              setPreviousLabel('bark_server', tx('barkServer'));
              setPreviousLabel('bark_critical_volume', tx('criticalVolume'));
              setPreviousLabel('bark_critical_sound', tx('criticalSound'));
              setPreviousLabel('serverchan_sendkey', tx('sendKey'));
              setPreviousLabel('bot_token', tx('botToken'));
              setPreviousLabel('chat_id', tx('chatId'));
              setPreviousLabel('smtp_host', tx('smtpHost'));
              setPreviousLabel('smtp_port', tx('smtpPort'));
              setCheckboxLabel('smtp_tls', tx('useSslTls'));
              setPreviousLabel('smtp_user', tx('smtpUsername'));
              setPreviousLabel('smtp_pass', tx('smtpPassword'));
              setPreviousLabel('email_from', tx('emailFrom'));
              setPreviousLabel('email_to', tx('emailTo'));
              setNodeText('#btn_bark_test', tx('testBark'));
              setNodeText('#btn_bark_sound_test', tx('applySound'));
              const criticalHelp = document.getElementById('bark_critical_enabled')?.closest('label')?.nextElementSibling;
              if (criticalHelp && criticalHelp.classList.contains('help')) criticalHelp.textContent = tx('criticalHelp');
              const soundHelp = document.getElementById('bark_sound_options')?.nextElementSibling;
              if (soundHelp && soundHelp.classList.contains('help')) soundHelp.textContent = tx('criticalSoundHelp');
              const localHelp = document.querySelector('#enable_local')?.closest('.settings-card')?.querySelector('.help');
              if (localHelp) localHelp.textContent = tx('localHelp');
              document.querySelectorAll('.settings-card .help').forEach(help => {
                if (help.querySelector('#smart_parallel_workers_val')) help.innerHTML = `${tx('current')}: <b><span id="smart_parallel_workers_val">${document.getElementById('smart_parallel_workers')?.value || ''}</span></b>（${tx('smartParallelHelp')}）`;
                if (help.querySelector('#loop_interval_val')) help.innerHTML = `${tx('current')}: <b><span id="loop_interval_val">${document.getElementById('loop_interval')?.value || ''}</span></b> ${tx('seconds')}（${tx('recommended120')}）`;
                if (help.querySelector('#per_hotel_delay_val')) help.innerHTML = `${tx('current')}: <b><span id="per_hotel_delay_val">${document.getElementById('per_hotel_delay')?.value || ''}</span></b> ${tx('seconds')}`;
                if (help.querySelector('#request_jitter_val')) help.innerHTML = `${tx('current')}: <b><span id="request_jitter_val">${document.getElementById('request_jitter')?.value || ''}</span></b>%`;
                if (help.querySelector('#alert_repeat_val')) help.innerHTML = `${tx('current')}: <b><span id="alert_repeat_val">${document.getElementById('alert_repeat')?.value || ''}</span></b> ${tx('times')}`;
                if (help.querySelector('#alert_interval_val')) help.innerHTML = `${tx('current')}: <b><span id="alert_interval_val">${document.getElementById('alert_interval')?.value || ''}</span></b> ${tx('seconds')}`;
                if (help.querySelector('#radius_km_val')) help.innerHTML = `${tx('current')}: <b><span id="radius_km_val">${document.getElementById('radius_km')?.value || ''}</span></b> km`;
                if (help.querySelector('#bark_critical_volume_val')) help.innerHTML = `${tx('current')}: <b><span id="bark_critical_volume_val">${document.getElementById('bark_critical_volume')?.value || ''}</span></b> / 10`;
              });
              const resultTitle = document.querySelector('.results-title');
              if (resultTitle) resultTitle.textContent = tx('resultTitle');
              setNodeText('.result-log-panel > summary', tx('availabilityLog'));
              const pushTitle = document.querySelector('.push-title');
              if (pushTitle) pushTitle.textContent = tx('pushStatus');
              setNodeText('.run-title', tx('runTitle'));
              setNodeText('.run-subtitle', tx('runSubtitle'));
              setAllText('.metric > span', [tx('status'), tx('loop'), tx('progress'), tx('uptime')]);
              setAllText('.result-stat span', [tx('available'), tx('unavailable'), tx('check'), tx('total')]);
              setAllText('.result-table:not(.result-log-table) th', [tx('code'), tx('hotel'), tx('status'), tx('minPrice'), tx('left'), tx('roomType')]);
              setAllText('.result-log-table th', [tx('code'), tx('hotel'), tx('availableSince'), tx('duration'), tx('minPrice'), tx('roomType')]);
              setNodeText('.push-subtitle', tx('pushSubtitle'));
              setNodeText('#btn_start', tx('start'));
              setNodeText('#btn_stop', tx('stop'));
              setNodeText('#btn_default', tx('defaults'));
              setNodeText('#btn_local_test', tx('testNotification'));
              const langLabels = LANG_OPTION_TEXT[lang] || LANG_OPTION_TEXT.zh_cn;
              setSelectOptions('primary_language', langLabels);
              setSelectOptions('smoking', {
                noSmoking: lang === 'ja' ? '禁煙 / Non-Smoking' : lang === 'ko' ? '금연 / Non-Smoking' : lang === 'zh_tw' ? '禁菸房 / Non-Smoking' : '无烟房 / Non-Smoking',
                Smoking: lang === 'ja' ? '喫煙 / Smoking' : lang === 'ko' ? '흡연 / Smoking' : lang === 'zh_tw' ? '吸菸房 / Smoking' : '吸烟房 / Smoking',
                all: lang === 'ja' ? '指定なし / Any' : lang === 'ko' ? '제한 없음 / Any' : lang === 'zh_tw' ? '不限制 / Any' : '不限制 / Any'
              });
              setSelectOptions('room_requirement', {
                any: lang === 'ja' ? '指定なし / Any' : lang === 'ko' ? '제한 없음 / Any' : lang === 'zh_tw' ? '不限制 / Any' : '不限制 / Any',
                single: lang === 'ja' ? 'シングル / Single' : lang === 'ko' ? '싱글 / Single' : lang === 'zh_tw' ? '單人房 / Single' : '单人房 / Single',
                double: lang === 'ja' ? 'ダブル / Double' : lang === 'ko' ? '더블 / Double' : lang === 'zh_tw' ? '雙人床房 / Double' : '大床房 / Double',
                twin: lang === 'ja' ? 'ツイン / Twin' : lang === 'ko' ? '트윈 / Twin' : lang === 'zh_tw' ? '雙床房 / Twin' : '双床房 / Twin'
              });
              setSelectOptions('membership_status', {
                member: lang === 'ja' ? '会員 / Member' : lang === 'ko' ? '회원 / Member' : lang === 'zh_tw' ? '會員 / Member' : '会员 / Member',
                non_member: lang === 'ja' ? '非会員 / Non-member' : lang === 'ko' ? '비회원 / Non-member' : lang === 'zh_tw' ? '非會員 / Non-member' : '非会员 / Non-member',
                unknown: lang === 'ja' ? '不明 / Unknown' : lang === 'ko' ? '알 수 없음 / Unknown' : lang === 'zh_tw' ? '未知 / Unknown' : '未知 / Unknown'
              });
              setSelectOptions('engine', {
                http: lang === 'ja' ? 'HTTP/API（推奨・軽量） / Recommended, lightweight' : lang === 'ko' ? 'HTTP/API (권장, 경량) / Recommended, lightweight' : lang === 'zh_tw' ? 'HTTP/API（推薦輕量） / Recommended, lightweight' : 'HTTP/API（推荐轻量） / Recommended, lightweight',
                playwright: lang === 'ja' ? 'Playwright（互換性重視） / Compatibility mode' : lang === 'ko' ? 'Playwright (호환성 우선) / Compatibility mode' : lang === 'zh_tw' ? 'Playwright（相容模式） / Compatibility mode' : 'Playwright（兼容模式） / Compatibility mode'
              });
              const region = document.getElementById('area_region');
              if (region && region.options.length) {
                Array.from(region.options).forEach((opt, idx) => {
                  if (idx === 0) opt.textContent = tx('selectRegion');
                  else {
                    const source = (AREA_INDEX.regions || []).find(x => String(x.id) === String(opt.value));
                    if (source) opt.textContent = localizedAreaLabel(source);
                  }
                });
              }
              const detail = document.getElementById('area_detail');
              if (detail && detail.disabled && detail.options.length) detail.options[0].textContent = tx('selectRegionFirst');
              const empty = document.querySelector('.hotel-picker-empty');
              if (empty) {
                const txt = empty.textContent || '';
                empty.textContent = txt.includes('matching') || txt.includes('匹配') || txt.includes('符合') || txt.includes('一致') || txt.includes('일치')
                  ? tx('noMatchingHotels')
                  : tx('noHotels');
              }
              syncDisplayValues();
              populateAreaDetails(true);
              renderPushStatus(LAST_PUSH_STATUS || []);
              refreshSearchHistory();
              if (LAST_UPDATE_STATUS) renderUpdateBanner(LAST_UPDATE_STATUS);
              if (Array.isArray(AREA_HOTELS)) renderSelectedHotelMap();
            }

            function renderProgress(p){
              if (!p) return;
              LAST_PROGRESS_STATE = {...p, client_ts: performance.now()};
              if (PROGRESS_ANIM_FRAME) cancelAnimationFrame(PROGRESS_ANIM_FRAME);
              const total = Math.max(0, Number(p.total||0));
              const done = Math.max(0, Math.min(Number(p.done||0), total));
              const waiting = p.phase === 'waiting';
              const waitTotal = Math.max(0, Number(p.wait_total_sec || 0));
              const waitElapsed = Math.max(0, Math.min(Number(p.wait_elapsed_sec || 0), waitTotal));
              const pct = waiting && waitTotal > 0 ? Math.round(waitElapsed*100/waitTotal) : (total>0 ? Math.round(done*100/total) : 0);
              document.getElementById('round-num').textContent = String(p.round||0);
              const bar = document.getElementById('prog-bar');
              bar.style.width = pct + '%';
              bar.className = 'progress-fill' + (waiting ? ' waiting' : '');
              document.getElementById('prog-text').textContent = waiting
                ? `${tx('waitingNext')}: ${Math.max(0, waitTotal - waitElapsed)}s (${pct}%)`
                : `${tx('progressText')}: ${done} / ${total} (${pct}%)`;
              const ratioEl = document.getElementById('progress-ratio');
              if (ratioEl) ratioEl.textContent = `${done} / ${total}`;
              const relH = (p && p.round_elapsed_human) ? p.round_elapsed_human : (Number(p.round_elapsed_sec||0) + 's');
              const upH  = (p && p.uptime_human) ? p.uptime_human : (Number(p.uptime_sec||0) + 's');
              document.getElementById('time-text').textContent = `${tx('loopElapsed')}: ${relH} | ${tx('uptime')}: ${upH}`;
              const uptimeEl = document.getElementById('uptime-text');
              if (uptimeEl) uptimeEl.textContent = upH;
              if (waiting && waitTotal > 0) startProgressSmoothing();
            }

            function startProgressSmoothing(){
              const tick = () => {
                const p = LAST_PROGRESS_STATE;
                if (!p || p.phase !== 'waiting') return;
                const bar = document.getElementById('prog-bar');
                if (!bar) return;
                const waitTotal = Math.max(0, Number(p.wait_total_sec || 0));
                const baseElapsed = Math.max(0, Number(p.wait_elapsed_sec || 0));
                const extra = Math.max(0, (performance.now() - Number(p.client_ts || performance.now())) / 1000);
                const elapsed = Math.min(waitTotal, baseElapsed + extra);
                const pct = waitTotal > 0 ? Math.round(elapsed * 1000 / waitTotal) / 10 : 0;
                bar.style.width = pct + '%';
                const remaining = Math.ceil(Math.max(0, waitTotal - elapsed));
                const progText = document.getElementById('prog-text');
                if (progText) progText.textContent = `${tx('waitingNext')}: ${remaining}s (${Math.round(pct)}%)`;
                if (elapsed < waitTotal) PROGRESS_ANIM_FRAME = requestAnimationFrame(tick);
              };
              PROGRESS_ANIM_FRAME = requestAnimationFrame(tick);
            }

            function renderSummary(cfg){
              return;
            }

            function pad2(n){ return (n<10? '0':'') + n; }
            function todayStr(){ const d=new Date(); return `${d.getFullYear()}-${pad2(d.getMonth()+1)}-${pad2(d.getDate())}`; }
            function plusOneDayStr(){ const d=new Date(); d.setDate(d.getDate()+1); return `${d.getFullYear()}-${pad2(d.getMonth()+1)}-${pad2(d.getDate())}`; }
            function dateStrFrom(d){ return `${d.getFullYear()}-${pad2(d.getMonth()+1)}-${pad2(d.getDate())}`; }
            function setDateRange(start, nights=1){
              const s = new Date(start);
              const e = new Date(start);
              e.setDate(e.getDate() + Math.max(1, Number(nights)||1));
              document.getElementById('start_date').value = dateStrFrom(s);
              document.getElementById('end_date').value = dateStrFrom(e);
              ['start_date','end_date'].forEach(markEdited);
              BLOCK_REMOTE_OVERWRITE = true;
            }
            function setNextWeekend(){
              const d = new Date();
              const day = d.getDay();
              let add = 0;
              if (day === 5 || day === 6 || day === 0) {
                add = 0;
              } else {
                add = (5 - day + 7) % 7;
              }
              d.setDate(d.getDate() + add);
              setDateRange(d, 1);
            }

            function selectedAreaCodes(){
              if (AREA_SELECTED_CODES instanceof Set) {
                const loaded = new Set(AREA_HOTELS.map(h => String(h.code || '')));
                return Array.from(AREA_SELECTED_CODES).filter(code => loaded.has(String(code)));
              }
              return Array.from(document.querySelectorAll('.area-hotel-check:checked')).map(el => el.value);
            }
            function selectedAreaHotels(){
              const selected = new Set(selectedAreaCodes());
              return AREA_HOTELS.filter(h => selected.has(String(h.code))).map(h => ({
                code: String(h.code || ''),
                name: h.name || '',
                name_primary: h.name_primary || '',
                name_zh: h.name_zh || '',
                name_zh_cn: h.name_zh_cn || h.name_zh || '',
                name_zh_tw: h.name_zh_tw || '',
                name_ja: h.name_ja || '',
                name_ko: h.name_ko || '',
                name_en: h.name_en || h.name || '',
                url: h.url || '',
                map_url: h.map_url || '',
                lat: h.lat ?? null,
                lng: h.lng ?? null,
                distance_km: h.distance_km ?? null
              }));
            }
            function currentSearchMode(){
              return document.querySelector('input[name="hotel_picker_mode"]:checked')?.value || 'area';
            }
            function selectedOptionText(id){
              const el = document.getElementById(id);
              if (!el || el.selectedIndex < 0) return '';
              return el.options[el.selectedIndex]?.textContent || '';
            }
            function collectPayload(){
              const selectedCodes = selectedAreaCodes();
              const barkKeyEl = document.getElementById('bark_key');
              const barkKeyValue = barkKeyEl ? barkKeyEl.value.trim().replace(/^\/+|\/+$/g, '') : '';
              return {
                start_date: document.getElementById('start_date').value,
                end_date: document.getElementById('end_date').value,
                people: Number(document.getElementById('people').value),
                rooms: Number(document.getElementById('rooms').value),
                smoking: document.getElementById('smoking').value,
                room_requirement: document.getElementById('room_requirement').value,
                membership_status: document.getElementById('membership_status').value,
                primary_language: document.getElementById('primary_language') ? document.getElementById('primary_language').value : 'zh_cn',
                hotel_codes: selectedCodes,
                hotel_codes_raw: '',
                selected_hotels: selectedAreaHotels(),
                search_mode: currentSearchMode(),
                area_region: document.getElementById('area_region') ? document.getElementById('area_region').value : '',
                area_detail: document.getElementById('area_detail') ? document.getElementById('area_detail').value : '',
                area_region_label: selectedOptionText('area_region'),
                area_detail_label: selectedOptionText('area_detail'),
                radius_query: document.getElementById('radius_query') ? document.getElementById('radius_query').value : '',
                radius_lat: document.getElementById('radius_lat') ? document.getElementById('radius_lat').value : '',
                radius_lng: document.getElementById('radius_lng') ? document.getElementById('radius_lng').value : '',
                radius_km: Number(document.getElementById('radius_km')?.value || 5),
                enable_telegram: document.getElementById('enable_telegram').checked,
                bot_token: document.getElementById('bot_token').value,
                chat_id: document.getElementById('chat_id').value,
                enable_bark: document.getElementById('enable_bark').checked,
                bark_key: barkKeyValue,
                bark_server: document.getElementById('bark_server').value,
                bark_critical_enabled: document.getElementById('bark_critical_enabled')?.checked || false,
                bark_critical_volume: Number(document.getElementById('bark_critical_volume')?.value || 5),
                bark_critical_sound: document.getElementById('bark_critical_sound')?.value || 'alarm',
                enable_serverchan: document.getElementById('enable_serverchan').checked,
                serverchan_sendkey: document.getElementById('serverchan_sendkey').value,
                enable_local: document.getElementById('enable_local').checked,
                enable_email: document.getElementById('enable_email').checked,
                smtp_host: document.getElementById('smtp_host').value,
                smtp_port: Number(document.getElementById('smtp_port').value),
                smtp_tls: document.getElementById('smtp_tls').checked,
                smtp_user: document.getElementById('smtp_user').value,
                smtp_pass: document.getElementById('smtp_pass').value,
                email_from: document.getElementById('email_from').value,
                email_to: document.getElementById('email_to').value,
                notify_available: document.getElementById('notify_available')?.checked ?? true,
                notify_unavailable: document.getElementById('notify_unavailable')?.checked ?? true,
                notify_availability_count_change: document.getElementById('notify_availability_count_change')?.checked ?? true,
                notify_start: document.getElementById('notify_start')?.checked ?? true,
                notify_stop: document.getElementById('notify_stop')?.checked ?? true,
                notify_search_error: document.getElementById('notify_search_error')?.checked || false,
                available_alert_repeat: Number(document.getElementById('alert_repeat').value),
                available_alert_repeat_interval_sec: Number(document.getElementById('alert_interval').value),
                loop_interval_seconds: Number(document.getElementById('loop_interval').value),
                per_hotel_delay_seconds: Number(document.getElementById('per_hotel_delay').value),
                request_jitter_percent: Number(document.getElementById('request_jitter').value),
                smart_parallel_enabled: document.getElementById('smart_parallel_enabled').checked,
                smart_parallel_workers: Number(document.getElementById('smart_parallel_workers').value),
                engine: (document.getElementById('engine') ? document.getElementById('engine').value : 'http')
              };
            }

            function validateBarkKeyInput(){
              const enabled = document.getElementById('enable_bark')?.checked;
              const el = document.getElementById('bark_key');
              if (!enabled || !el) return true;
              let value = (el.value || '').trim().replace(/^\/+|\/+$/g, '');
              if (value.startsWith('http://') || value.startsWith('https://')) {
                try {
                  const parsed = new URL(value);
                  const parts = parsed.pathname.split('/').filter(Boolean);
                  value = parts[0] || '';
                } catch(e) {}
              }
              if (value.length > 48) {
                document.getElementById('err').textContent = tx('barkKeyTooLong');
                document.getElementById('msg').textContent = '';
                el.focus();
                return false;
              }
              if (value && value.length < 8) {
                document.getElementById('err').textContent = tx('barkKeyTooShort');
                document.getElementById('msg').textContent = '';
                el.focus();
                return false;
              }
              return true;
            }

            function setIfNotFocused(id, value){
              if (value === undefined) return;
              if (BLOCK_REMOTE_OVERWRITE) return;
              const el = document.getElementById(id);
              if (!el) return;
              if (document.activeElement === el) return;
              if (recentlyEdited(id)) return;
              if (id === 'smtp_pass') return;
              el.value = value;
            }
            function setValueIfExists(id, value){
              const el = document.getElementById(id);
              if (el) el.value = value == null ? '' : value;
            }

            ['start_date','end_date','people','rooms','smoking','room_requirement','membership_status','primary_language','engine',
             'smart_parallel_enabled','smart_parallel_workers',
             'enable_telegram','bot_token','chat_id','enable_bark','bark_key','bark_server','bark_critical_enabled','bark_critical_volume','bark_critical_sound','enable_serverchan','serverchan_sendkey',
             'enable_local','enable_email','smtp_host','smtp_port','smtp_tls','smtp_user','smtp_pass','email_from','email_to',
             'notify_available','notify_unavailable','notify_availability_count_change','notify_start','notify_stop','notify_search_error',
             'alert_repeat','alert_interval','loop_interval','per_hotel_delay','request_jitter','area_region','area_detail','area_filter','radius_query','radius_km','radius_lat','radius_lng'
            ].forEach(id=>{
              const el = document.getElementById(id);
              if(!el) return;
              el.addEventListener('input', ()=>{ markEdited(id); BLOCK_REMOTE_OVERWRITE = true; });
              el.addEventListener('change', ()=>{ markEdited(id); BLOCK_REMOTE_OVERWRITE = true; });
            });

            ['alert_repeat','alert_interval','loop_interval','per_hotel_delay','request_jitter','smart_parallel_workers','radius_km','bark_critical_volume'].forEach(id=>{
              const el = document.getElementById(id);
              if(!el) return;
              el.addEventListener('input', syncDisplayValues);
              el.addEventListener('change', syncDisplayValues);
            });
            // Initial sync
            syncDisplayValues();
            applyUiLanguage();
            function syncDisplayValues(){
              const ar = document.getElementById('alert_repeat');
              const ai = document.getElementById('alert_interval');
              const li = document.getElementById('loop_interval');
              const rj = document.getElementById('request_jitter');
              const spw = document.getElementById('smart_parallel_workers');
              const rk = document.getElementById('radius_km');
              const bcv = document.getElementById('bark_critical_volume');
              const arv = document.getElementById('alert_repeat_val');
              const aiv = document.getElementById('alert_interval_val');
              const liv = document.getElementById('loop_interval_val');
              const phd = document.getElementById('per_hotel_delay');
              const phdv = document.getElementById('per_hotel_delay_val');
              const rjv = document.getElementById('request_jitter_val');
              const spwv = document.getElementById('smart_parallel_workers_val');
              const rkv = document.getElementById('radius_km_val');
              const bcvv = document.getElementById('bark_critical_volume_val');
              if (ar && arv) arv.textContent = Number(ar.value) >= 11 ? 'INF' : String(ar.value);
              if (ai && aiv) aiv.textContent = String(ai.value);
              if (li && liv) liv.textContent = String(li.value);
              if (phd && phdv) phdv.textContent = String(phd.value);
              if (rj && rjv) rjv.textContent = String(rj.value);
              if (spw && spwv) spwv.textContent = String(spw.value);
              if (rk && rkv) rkv.textContent = String(rk.value);
              if (bcv && bcvv) bcvv.textContent = String(bcv.value);
            }

            var AREA_INDEX = null;
            var AREA_HOTELS = [];
            var AREA_SELECTED_CODES = null;
            var LAST_PUSH_STATUS = [];
            var LAST_UPDATE_STATUS = null;
            var AREA_SELECTED_MAP = null;
            var AREA_SELECTED_MARKERS = [];
            function escText(s){
              return String(s == null ? '' : s).replace(/[&<>"']/g, (m) => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
              }[m]));
            }
            function setAreaStatus(text, isError=false){
              const el = document.getElementById('area_status');
              if (!el) return;
              el.textContent = text;
              el.style.color = isError ? '#a33a3a' : '#777';
            }
            function validMapCoord(h){
              const lat = Number(h && h.lat);
              const lng = Number(h && h.lng);
              if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
              if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
              return {lat, lng};
            }
            function mapStatusText(coordCount, selectedCount){
              if (coordCount <= 0 && selectedCount > 0) {
                return tx('noSelectedHotelCoords');
              }
              return fmt('showingSelectedHotels', {count: coordCount});
            }
            function clearSelectedHotelMap(){
              if (AREA_SELECTED_MAP && Array.isArray(AREA_SELECTED_MARKERS)) {
                AREA_SELECTED_MARKERS.forEach(marker => {
                  try { AREA_SELECTED_MAP.removeLayer(marker); } catch(e) {}
                });
              }
              AREA_SELECTED_MARKERS = [];
            }
            function renderSelectedHotelMap(){
              const panel = document.getElementById('area_map_panel');
              const status = document.getElementById('area_map_status');
              const mapEl = document.getElementById('area_selected_map');
              if (!panel || !status || !mapEl) return;
              const selected = selectedAreaHotels();
              const withCoords = selected.map(h => ({hotel: h, coord: validMapCoord(h)})).filter(x => x.coord);
              if (!AREA_HOTELS.length || selected.length === 0){
                panel.hidden = true;
                clearSelectedHotelMap();
                return;
              }
              panel.hidden = false;
              status.textContent = mapStatusText(withCoords.length, selected.length);
              if (!withCoords.length){
                clearSelectedHotelMap();
                return;
              }
              if (typeof L === 'undefined'){
                status.textContent = tx('mapLibraryMissing');
                return;
              }
              if (!AREA_SELECTED_MAP){
                AREA_SELECTED_MAP = L.map(mapEl, {scrollWheelZoom: false});
                L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
                  maxZoom: 19,
                  attribution: '&copy; OpenStreetMap contributors'
                }).addTo(AREA_SELECTED_MAP);
              }
              clearSelectedHotelMap();
              const points = [];
              withCoords.forEach(({hotel, coord}) => {
                const name = bilingualText(hotel.name_primary || hotel.name_zh || hotel.name || '', hotel.name_en || hotel.name || '(Hotel name not found)');
                const popup = `
                  <div class="map-popup-title">${escText(hotel.code)} · ${escText(name)}</div>
                  <div class="map-popup-links">
                    <a href="${escText(hotel.url || '#')}" target="_blank" rel="noreferrer noopener">${escText(tx('official'))}</a>
                    ${hotel.map_url ? `<a href="${escText(hotel.map_url)}" target="_blank" rel="noreferrer noopener">${escText(tx('openMap'))}</a>` : ''}
                  </div>
                `;
                const marker = L.marker([coord.lat, coord.lng]).addTo(AREA_SELECTED_MAP).bindPopup(popup);
                AREA_SELECTED_MARKERS.push(marker);
                points.push([coord.lat, coord.lng]);
              });
              setTimeout(() => {
                try {
                  AREA_SELECTED_MAP.invalidateSize();
                  if (points.length === 1) AREA_SELECTED_MAP.setView(points[0], 13);
                  else AREA_SELECTED_MAP.fitBounds(points, {padding: [28, 28], maxZoom: 13});
                } catch(e) {}
              }, 0);
            }
            function setPickerMode(mode){
              const next = mode === 'radius' ? 'radius' : 'area';
              document.querySelectorAll('input[name="hotel_picker_mode"]').forEach(el => { el.checked = el.value === next; });
              document.getElementById('area_mode_panel')?.classList.toggle('active', next === 'area');
              document.getElementById('radius_mode_panel')?.classList.toggle('active', next === 'radius');
              setAreaStatus(next === 'radius'
                ? tx('radiusModeStatus')
                : tx('areaHint'));
            }
            async function initAreaPicker(){
              try{
                const r = await fetch('/area_index');
                const j = await r.json();
                if (!j.ok) throw new Error('area index failed');
                AREA_INDEX = j.data || {regions: []};
                const region = document.getElementById('area_region');
                if (!region) return;
                const regions = Array.isArray(AREA_INDEX.regions) ? AREA_INDEX.regions : [];
                region.innerHTML = `<option value="">${escText(tx('selectRegion'))}</option>` + regions.map(x =>
                  `<option value="${escText(x.id)}">${escText(localizedAreaLabel(x))}</option>`
                ).join('');
              }catch(e){
                setAreaStatus(tx('areaIndexFailed') + e, true);
              }
            }
            function populateAreaDetails(preserveHotels=false){
              const regionSel = document.getElementById('area_region');
              const detailSel = document.getElementById('area_detail');
              if (!regionSel || !detailSel || !AREA_INDEX) return;
              const previousDetail = detailSel.value;
              const regionId = Number(regionSel.value || 0);
              const region = (AREA_INDEX.regions || []).find(x => Number(x.id) === regionId);
	              if (!preserveHotels) {
	                AREA_HOTELS = [];
	                AREA_SELECTED_CODES = null;
	                renderAreaHotels();
	              }
              if (!region){
                detailSel.disabled = true;
                detailSel.innerHTML = `<option value="">${escText(tx('selectRegionFirst'))}</option>`;
              setAreaStatus(tx('areaHint'));
                renderSelectedHotelMap();
                return;
              }
              const regionParts = localizedAreaParts(region);
              const options = [`<option value="">${escText(allOfLabel(regionParts.primary, regionParts.en || region.name))}</option>`];
              const showPrefAll = (region.prefectures || []).length > 1;
              (region.prefectures || []).forEach(pref => {
                const prefParts = localizedAreaParts(pref);
                const prefLabel = bilingualText(prefParts.primary, prefParts.en || pref.name);
                if (showPrefAll) {
                  options.push(`<option value="pref-${escText(pref.id)}">${escText(allOfLabel(prefParts.primary, prefParts.en || pref.name))}</option>`);
                }
                (pref.areas || []).forEach(area => {
                  const areaLabel = localizedAreaLabel(area);
                  options.push(`<option value="area-${escText(area.id)}">${escText(prefLabel || pref.name)} - ${escText(areaLabel || area.name)}</option>`);
                });
              });
              detailSel.disabled = false;
              detailSel.innerHTML = options.join('');
              if (preserveHotels && previousDetail) detailSel.value = previousDetail;
              setAreaStatus(tx('areaSelected'));
            }
            function renderAreaHotels(){
              const wrap = document.getElementById('area_hotels');
              const filter = (document.getElementById('area_filter')?.value || '').trim().toLowerCase();
              if (!wrap) return;
              if (AREA_HOTELS.length && !(AREA_SELECTED_CODES instanceof Set)) {
                AREA_SELECTED_CODES = new Set(AREA_HOTELS.map(h => String(h.code || '')));
              }
              const hotels = AREA_HOTELS.filter(h => {
                if (!filter) return true;
                return String(h.code || '').toLowerCase().includes(filter)
                  || String(h.name || '').toLowerCase().includes(filter)
                  || String(h.name_en || '').toLowerCase().includes(filter)
                  || String(h.name_primary || '').toLowerCase().includes(filter)
                  || String(h.name_zh || '').toLowerCase().includes(filter)
                  || String(h.name_zh_cn || '').toLowerCase().includes(filter)
                  || String(h.name_zh_tw || '').toLowerCase().includes(filter)
                  || String(h.name_ja || '').toLowerCase().includes(filter)
                  || String(h.name_ko || '').toLowerCase().includes(filter);
              });
              if (!hotels.length){
                wrap.innerHTML = `<div class="hotel-picker-empty">${escText(tx('noMatchingHotels'))}</div>`;
                renderSelectedHotelMap();
                return;
              }
              wrap.innerHTML = hotels.map(h => `
                <div class="hotel-item">
                  <label>
	                    <input class="area-hotel-check" type="checkbox" value="${escText(h.code)}" ${AREA_SELECTED_CODES?.has(String(h.code || '')) ? 'checked' : ''}>
                    <span class="hotel-code">${escText(h.code)}</span>
                    <span class="hotel-name hotel-actions">
                      <span>
                        <a href="${escText(h.url || '#')}" target="_blank" rel="noreferrer noopener">${escText(bilingualText(h.name_primary || h.name_zh || h.name || '', h.name_en || h.name || '(Hotel name not found)'))}</a>
                        ${h.distance_km != null ? `<span class="distance-badge">${escText(h.distance_km)} km</span>` : ''}
                      </span>
                      <a class="hotel-map" href="${escText(h.map_url || '#')}" target="_blank" rel="noreferrer noopener">${escText(tx('openMap'))}</a>
                    </span>
	                  </label>
	                </div>
	              `).join('');
              wrap.querySelectorAll('.area-hotel-check').forEach(el => {
                el.addEventListener('change', () => {
                  if (!(AREA_SELECTED_CODES instanceof Set)) AREA_SELECTED_CODES = new Set();
                  if (el.checked) AREA_SELECTED_CODES.add(String(el.value));
                  else AREA_SELECTED_CODES.delete(String(el.value));
                  renderSelectedHotelMap();
                });
              });
              renderSelectedHotelMap();
            }
            async function loadAreaHotels(){
              const regionSel = document.getElementById('area_region');
              const detailSel = document.getElementById('area_detail');
              const regionId = Number(regionSel?.value || 0);
              if (!regionId){
                setAreaStatus(tx('selectRegionFirst'), true);
                return;
              }
              setAreaStatus(tx('loadingHotels'));
              try{
                const r = await fetch('/area_hotels', {
                  method:'POST',
                  headers:{'Content-Type':'application/json'},
                  body: JSON.stringify({region_id: regionId, detail_id: detailSel?.value || '', primary_language: document.getElementById('primary_language')?.value || 'zh_cn'})
                });
                const j = await r.json();
                if (!j.ok) throw new Error(j.error || 'load failed');
                AREA_HOTELS = Array.isArray(j.hotels) ? j.hotels : [];
                AREA_SELECTED_CODES = new Set(AREA_HOTELS.map(h => String(h.code || '')));
                renderAreaHotels();
                const n = AREA_HOTELS.length;
                setAreaStatus(fmt('loadedHotels', {count: n}));
	              }catch(e){
	                AREA_HOTELS = [];
	                AREA_SELECTED_CODES = null;
	                renderAreaHotels();
                setAreaStatus(tx('hotelLoadingFailed') + e, true);
              }
            }
            async function loadRadiusHotels(){
              const query = (document.getElementById('radius_query')?.value || '').trim();
              const radiusKm = Number(document.getElementById('radius_km')?.value || 5);
              if (!query){
                setAreaStatus(tx('addressRequired'), true);
                return;
              }
              const looksLikeCoord = /^\\s*-?\\d+(?:\\.\\d+)?\\s*[,，\\s]\\s*-?\\d+(?:\\.\\d+)?\\s*$/.test(query);
              setAreaStatus(looksLikeCoord
                ? tx('filteringByCoords')
                : tx('geocodingAddress'));
              try{
                const r = await fetch('/radius_hotels', {
                  method:'POST',
                  headers:{'Content-Type':'application/json'},
                  body: JSON.stringify({query, radius_km: radiusKm, primary_language: document.getElementById('primary_language')?.value || 'zh_cn'})
                });
                const j = await r.json();
                if (!j.ok) throw new Error(j.error || 'radius load failed');
                AREA_HOTELS = Array.isArray(j.hotels) ? j.hotels : [];
                AREA_SELECTED_CODES = new Set(AREA_HOTELS.map(h => String(h.code || '')));
                if (j.center){
                  document.getElementById('radius_lat').value = j.center.lat ?? '';
                  document.getElementById('radius_lng').value = j.center.lng ?? '';
                }
                renderAreaHotels();
                const n = AREA_HOTELS.length;
                const centerText = j.center ? `${j.center.lat}, ${j.center.lng}` : query;
                setAreaStatus(fmt('loadedHotelsCenter', {count: n, center: centerText}));
	              }catch(e){
	                AREA_HOTELS = [];
	                AREA_SELECTED_CODES = null;
	                renderAreaHotels();
                setAreaStatus(tx('radiusSearchFailed') + e, true);
              }
            }
            function setAreaHotelChecks(checked){
              AREA_SELECTED_CODES = checked ? new Set(AREA_HOTELS.map(h => String(h.code || ''))) : new Set();
              document.querySelectorAll('.area-hotel-check').forEach(el => { el.checked = checked; });
              renderSelectedHotelMap();
            }
            initAreaPicker();
            setPickerMode(currentSearchMode());

            function historyHotelList(record){
              const hotels = Array.isArray(record.selected_hotels) ? record.selected_hotels : [];
              if (hotels.length) return hotels.map(h => ({
                code: String(h.code || ''),
                name: h.name || h.name_en || h.name_zh || '',
                name_primary: h.name_primary || '',
                name_zh: h.name_zh || '',
                name_zh_cn: h.name_zh_cn || h.name_zh || '',
                name_zh_tw: h.name_zh_tw || '',
                name_ja: h.name_ja || '',
                name_ko: h.name_ko || '',
                name_en: h.name_en || h.name || '',
                url: h.url || `https://www.toyoko-inn.com/eng/search/detail/${String(h.code || '').padStart(5,'0')}/`,
                map_url: h.map_url || '',
                lat: h.lat ?? null,
                lng: h.lng ?? null,
                distance_km: h.distance_km ?? null
              })).filter(h => h.code);
              return (Array.isArray(record.hotel_codes) ? record.hotel_codes : []).map(code => ({
                code: String(code),
                name: '',
                name_zh: '',
                name_en: '',
                url: `https://www.toyoko-inn.com/eng/search/detail/${String(code).padStart(5,'0')}/`,
                map_url: '',
                lat: null,
                lng: null,
                distance_km: null
              }));
            }
            function renderSearchHistory(records){
              const wrap = document.getElementById('search_history');
              if (!wrap) return;
              if (!Array.isArray(records) || records.length === 0){
                wrap.innerHTML = `<div class="history-empty">${escText(tx('noHistory'))}</div>`;
                return;
              }
              wrap.innerHTML = records.slice(0, 10).map((r, idx) => {
                const count = Array.isArray(r.hotel_codes) ? r.hotel_codes.length : 0;
                const useStoredAreaText = currentLang() === 'zh_cn' || currentLang() === 'zh_tw';
                const region = useStoredAreaText && r.area_region_label ? r.area_region_label : historyAreaFallback('region', r.area_region);
                const detail = useStoredAreaText && r.area_detail_label ? r.area_detail_label : historyAreaFallback('detail', r.area_detail);
                const scope = r.search_mode === 'radius'
                  ? `${escText(r.radius_query || '')} · ${escText(r.radius_km || 5)} km`
                  : `${escText(region)} · ${escText(detail)}`;
                const title = currentLang() === 'ja'
                  ? `${escText(r.start_date || '')} → ${escText(r.end_date || '')} · ${count} 件のホテル / ${count} hotels`
                  : currentLang() === 'ko'
                    ? `${escText(r.start_date || '')} → ${escText(r.end_date || '')} · ${count}개 호텔 / ${count} hotels`
                    : currentLang() === 'zh_tw'
                      ? `${escText(r.start_date || '')} → ${escText(r.end_date || '')} · ${count} 家飯店 / ${count} hotels`
                      : `${escText(r.start_date || '')} → ${escText(r.end_date || '')} · ${count} 家酒店 / ${count} hotels`;
                const meta = scope;
                const params = `${escText(r.people || 1)}${escText(tx('guestUnit'))} · ${escText(r.rooms || 1)}${escText(tx('roomUnit'))} · ${escText(r.smoking || 'all')} · ${escText(r.room_requirement || 'any')} · ${escText(r.membership_status || 'member')} · ${escText(r.primary_language || 'zh_cn')}`;
                return `<div class="history-item">
                  <div>
                    <div class="history-title">${title}</div>
                    <div class="history-meta">${meta}</div>
                    <div class="history-meta">${params}</div>
                    <div class="history-meta">${escText(r.created_at || '')}</div>
                  </div>
                  <button class="history-use" data-history-index="${idx}">${escText(tx('useHistory'))}</button>
                </div>`;
              }).join('');
              wrap.querySelectorAll('[data-history-index]').forEach(btn => {
                btn.addEventListener('click', (e) => {
                  e.preventDefault();
                  const record = records[Number(btn.getAttribute('data-history-index'))];
                  applySearchHistory(record);
                });
              });
            }
            async function refreshSearchHistory(){
              try{
                const r = await fetch('/search_history');
                const j = await r.json();
                renderSearchHistory(j.records || []);
              }catch(e){
                renderSearchHistory([]);
              }
            }
            async function clearSearchHistory(){
              try{
                await fetch('/search_history/clear', {method:'POST'});
                await refreshSearchHistory();
              }catch(e){
                document.getElementById('err').textContent = String(e);
	              }
	            }
            function setPanelOpen(selector, open){
              document.querySelectorAll(selector).forEach(panel => {
                setDetailsOpen(panel, !!open);
              });
            }
            function setDetailsOpen(panel, open){
              if (!panel || panel.tagName !== 'DETAILS') return;
              const content = panel.querySelector(':scope > .details-content');
              if (!content || panel.open === open) {
                panel.open = open;
                return;
              }
              panel.classList.add('animating');
              if (open) {
                panel.open = true;
                content.style.maxHeight = '0px';
                requestAnimationFrame(() => {
                  content.style.maxHeight = content.scrollHeight + 'px';
                });
                setTimeout(() => {
                  content.style.maxHeight = '';
                  panel.classList.remove('animating');
                }, 310);
              } else {
                content.style.maxHeight = content.scrollHeight + 'px';
                requestAnimationFrame(() => {
                  content.style.maxHeight = '0px';
                });
                setTimeout(() => {
                  panel.open = false;
                  content.style.maxHeight = '';
                  panel.classList.remove('animating');
                }, 310);
              }
            }
            function initAnimatedDetails(){
              document.querySelectorAll('details').forEach(detail => {
                if (detail.classList.contains('details-animated')) return;
                const summary = detail.querySelector(':scope > summary');
                if (!summary) return;
                const wrapper = document.createElement('div');
                wrapper.className = 'details-content';
                while (summary.nextSibling) wrapper.appendChild(summary.nextSibling);
                detail.appendChild(wrapper);
                detail.classList.add('details-animated');
                summary.addEventListener('click', (event) => {
                  event.preventDefault();
                  setDetailsOpen(detail, !detail.open);
                });
              });
            }
            function collapseSearchPanels(){
              setPanelOpen('#search_panel, #area_picker_panel, details.settings-panel', false);
            }
            function expandSearchAreaPicker(){
              setPanelOpen('#search_panel, #area_picker_panel', true);
              setTimeout(() => {
                try {
                  if (AREA_SELECTED_MAP) AREA_SELECTED_MAP.invalidateSize();
                } catch(e) {}
              }, 0);
            }
            function applySearchHistory(record){
              if (!record) return;
              const setValue = (id, value) => { const el = document.getElementById(id); if (el) el.value = value; };
              setValue('start_date', record.start_date || todayStr());
              setValue('end_date', record.end_date || plusOneDayStr());
              setValue('people', record.people || 1);
              setValue('rooms', record.rooms || 1);
              setValue('smoking', record.smoking || 'all');
              setValue('room_requirement', record.room_requirement || 'any');
              setValue('membership_status', record.membership_status || 'member');
              setValue('primary_language', record.primary_language || 'zh_cn');
              setValue('engine', record.engine || 'http');
              const parallelEl = document.getElementById('smart_parallel_enabled');
              if (parallelEl) parallelEl.checked = !!record.smart_parallel_enabled;
              setValue('smart_parallel_workers', record.smart_parallel_workers || 1);
              setValue('loop_interval', record.loop_interval_seconds || 30);
              setValue('per_hotel_delay', record.per_hotel_delay_seconds || 1);
              setValue('request_jitter', record.request_jitter_percent == null ? 40 : record.request_jitter_percent);
              setValue('alert_repeat', record.available_alert_repeat ?? 0);
              setValue('alert_interval', record.available_alert_repeat_interval_sec || 300);
              setValue('radius_query', record.radius_query || '');
              setValue('radius_lat', record.radius_lat || '');
              setValue('radius_lng', record.radius_lng || '');
              setValue('radius_km', record.radius_km || 5);
              setPickerMode(record.search_mode || 'area');
              const region = document.getElementById('area_region');
              if (region && record.area_region) {
                region.value = record.area_region;
                populateAreaDetails();
                const detail = document.getElementById('area_detail');
                if (detail && record.area_detail) detail.value = record.area_detail;
	              }
	              AREA_HOTELS = historyHotelList(record);
	              AREA_SELECTED_CODES = new Set(AREA_HOTELS.map(h => String(h.code || '')));
	              renderAreaHotels();
              syncDisplayValues();
              setAreaStatus(fmt('loadedHistory', {count: AREA_HOTELS.length}));
              Object.keys(EDIT_TS).forEach(k => delete EDIT_TS[k]);
              BLOCK_REMOTE_OVERWRITE = true;
            }

            function restoreAreaFromConfig(cfg){
              if (!cfg || BLOCK_REMOTE_OVERWRITE) return;
              const hotels = Array.isArray(cfg.selected_hotels) ? cfg.selected_hotels : [];
              if (hotels.length && AREA_HOTELS.length === 0){
                setValueIfExists('radius_query', cfg.radius_query || '');
                setValueIfExists('radius_lat', cfg.radius_lat || '');
                setValueIfExists('radius_lng', cfg.radius_lng || '');
                setValueIfExists('radius_km', cfg.radius_km || 5);
                setPickerMode(cfg.search_mode || 'area');
                const region = document.getElementById('area_region');
                if (region && cfg.area_region) {
                  region.value = cfg.area_region;
                  populateAreaDetails();
                  const detail = document.getElementById('area_detail');
                  if (detail && cfg.area_detail) detail.value = cfg.area_detail;
                }
	                AREA_HOTELS = historyHotelList({
	                  selected_hotels: hotels,
	                  hotel_codes: cfg.hotel_codes || []
	                });
	                AREA_SELECTED_CODES = new Set(AREA_HOTELS.map(h => String(h.code || '')));
	                renderAreaHotels();
                setAreaStatus(fmt('restoredHotels', {count: AREA_HOTELS.length}));
              }
            }

            async function callStart(){
              const payload = collectPayload();
              if (!validateBarkKeyInput()) return;
              if (!Array.isArray(payload.hotel_codes) || payload.hotel_codes.length === 0){
                document.getElementById('err').textContent = tx('selectHotelsFirst');
                document.getElementById('msg').textContent = '';
                return;
              }
              try {
                const r = await fetch('/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
                const j = await r.json();
                if (j.ok) {
                  document.getElementById('msg').textContent = j.restarted ? tx('restartedMessage') : tx('startedMessage');
                  document.getElementById('err').textContent = '';
	                  document.getElementById('running-pill').textContent = tx('running');
	                  document.getElementById('running-pill').className = 'pill on';
	                  collapseSearchPanels();
	                  refreshSearchHistory();
                } else {
                  document.getElementById('err').textContent = tx('failedToStart');
                  document.getElementById('msg').textContent = '';
                }
                refreshStatus();
              } catch(e) {
                document.getElementById('err').textContent = e;
                document.getElementById('msg').textContent = '';
              }
            }
            async function callStop(){
              try {
                const r = await fetch('/stop', {method:'POST'});
                const j = await r.json();
                if (j.ok) {
                  document.getElementById('msg').textContent = tx('stoppedMessage');
                  document.getElementById('err').textContent = '';
	                  document.getElementById('running-pill').textContent = tx('stopped');
	                  document.getElementById('running-pill').className = 'pill off';
	                  expandSearchAreaPicker();
                } else {
                  document.getElementById('err').textContent = tx('failedToStop');
                  document.getElementById('msg').textContent = '';
                }
              } catch(e) {
                document.getElementById('err').textContent = e;
                document.getElementById('msg').textContent = '';
              }
            }
            async function callLocalTest(){
              try{
                const payload = collectPayload();
                const r = await fetch('/local_notify_test', {
                  method:'POST',
                  headers:{'Content-Type':'application/json'},
                  body: JSON.stringify(payload)
                });
                const j = await r.json();
                if (j.ok){
                  document.getElementById('msg').textContent = tx('testNotificationSent');
                  document.getElementById('err').textContent = '';
                } else {
                  document.getElementById('err').textContent = j.error || tx('testNotificationFailed');
                  document.getElementById('msg').textContent = '';
                }
              }catch(e){
                document.getElementById('err').textContent = String(e);
                document.getElementById('msg').textContent = '';
              }
            }
            async function callBarkTest(){
              try{
                const payload = collectPayload();
                if (!validateBarkKeyInput()) return;
                const r = await fetch('/bark_notify_test', {
                  method:'POST',
                  headers:{'Content-Type':'application/json'},
                  body: JSON.stringify(payload)
                });
                const j = await r.json();
                if (j.ok){
                  document.getElementById('msg').textContent = tx('barkTestSent');
                  document.getElementById('err').textContent = '';
                } else {
                  document.getElementById('err').textContent = j.error || tx('barkTestFailed');
                  document.getElementById('msg').textContent = '';
                }
              }catch(e){
                document.getElementById('err').textContent = String(e);
                document.getElementById('msg').textContent = '';
              }
            }
            async function callBarkSoundTest(){
              try{
                const soundEl = document.getElementById('bark_critical_sound');
                if (soundEl && !(soundEl.value || '').trim()) soundEl.value = 'alarm';
                const criticalEl = document.getElementById('bark_critical_enabled');
                if (criticalEl) criticalEl.checked = true;
                const payload = collectPayload();
                payload.bark_critical_enabled = true;
                payload.bark_critical_sound = (payload.bark_critical_sound || 'alarm').trim();
                if (!validateBarkKeyInput()) return;
                const r = await fetch('/bark_sound_test', {
                  method:'POST',
                  headers:{'Content-Type':'application/json'},
                  body: JSON.stringify(payload)
                });
                const j = await r.json();
                if (j.ok){
                  document.getElementById('msg').textContent = fmt('barkSoundSent', {sound: payload.bark_critical_sound});
                  document.getElementById('err').textContent = '';
                  refreshStatus();
                } else {
                  document.getElementById('err').textContent = j.error || tx('barkSoundFailed');
                  document.getElementById('msg').textContent = '';
                }
              }catch(e){
                document.getElementById('err').textContent = String(e);
                document.getElementById('msg').textContent = '';
              }
            }

            function renderUpdateBanner(update){
              LAST_UPDATE_STATUS = update;
              const banner = document.getElementById('update-banner');
              if (!banner || !update) return;
              const title = document.getElementById('update-title');
              const message = document.getElementById('update-message');
              const button = document.getElementById('btn_upgrade');
              const state = update.state || 'idle';
              if (state === 'update_available') {
                banner.hidden = false;
                if (title) title.textContent = tx('updateAvailableTitle');
                if (message) message.textContent = fmt('updateAvailableMessage', {current: update.current_version || '-', latest: update.latest_version || '-'});
                if (button) {
                  button.hidden = false;
                  button.disabled = false;
                  button.textContent = tx('updateButton');
                }
              } else if (state === 'upgrading') {
                banner.hidden = false;
                if (title) title.textContent = tx('upgradingTitle');
                if (message) message.textContent = tx('upgradingMessage');
                if (button) {
                  button.hidden = false;
                  button.disabled = true;
                  button.textContent = tx('updatingButton');
                }
              } else if (state === 'upgraded') {
                banner.hidden = false;
                if (title) title.textContent = tx('upgradedTitle');
                if (message) message.textContent = tx('upgradedMessage');
                if (button) button.hidden = true;
              } else {
                banner.hidden = true;
              }
            }

            async function refreshUpdateStatus(){
              try{
                const r = await fetch('/update_status');
                const j = await r.json();
                renderUpdateBanner(j.update || null);
              }catch(e){}
            }

            async function callUpgrade(){
              try{
                const button = document.getElementById('btn_upgrade');
                if (button) button.disabled = true;
                const r = await fetch('/upgrade', {method:'POST'});
                const j = await r.json();
                renderUpdateBanner(j.update || null);
              }catch(e){
                const err = document.getElementById('err');
                if (err) err.textContent = String(e);
              }
            }

            function setRunning(is){
              const pill = document.getElementById('running-pill');
              pill.textContent = is ? tx('running') : tx('stopped');
              pill.className = 'pill ' + (is ? 'on' : 'off');
            }

            function statusInfo(r, status){
                if (status === '✅' || r.available === true) return {cls:'available', row:'row-available', label:tx('available')};
                if (status === '❌' || r.available === false) return {cls:'unavailable', row:'row-unavailable', label:tx('unavailable')};
                if (status === '❗' || r.requirement_unmet) return {cls:'warn', row:'', label:tx('check')};
                return {cls:'unknown', row:'', label:tx('check')};
            }

            function setResultStats(results){
                const stats = {available:0, unavailable:0, unknown:0, total:0};
                if (Array.isArray(results)){
                    results.forEach(r => {
                        stats.total += 1;
                        if (r.available === true && !r.requirement_unmet) stats.available += 1;
                        else if (r.available === false && !r.requirement_unmet) stats.unavailable += 1;
                        else stats.unknown += 1;
                    });
                }
                const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = String(val); };
                set('stat-available', stats.available);
                set('stat-unavailable', stats.unavailable);
                set('stat-unknown', stats.unknown);
                set('stat-total', stats.total);
            }

            function renderPushStatus(items){
                const grid = document.getElementById('push-status-grid');
                if (!grid) return;
                LAST_PUSH_STATUS = Array.isArray(items) ? items : [];
                const stateLabel = {
                    waiting: tx('waiting'),
                    pushing: tx('pushing'),
                    success: tx('success'),
                    failed: tx('failed'),
                    disabled: tx('disabled')
                };
                const safe = (s) => String(s || '').replace(/[&<>"']/g, (m) => ({
                    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
                }[m]));
                const localizedMessage = (message) => {
                    const raw = String(message || '').trim();
                    if (!raw) return '';
                    if (raw === 'sent OK') return tx('sentOk');
                    if (raw === 'terminal-notifier sent OK') return tx('terminalNotifierSentOk');
                    if (raw === 'osascript sent OK') return tx('osascriptSentOk');
                    return raw;
                };
                if (!Array.isArray(items) || items.length === 0){
                    grid.innerHTML = `<div class="push-card"><div class="push-name">${safe(tx('noChannels'))}</div><div class="push-enabled">${safe(tx('notConfigured'))}</div><span class="push-chip disabled">${safe(tx('disabled'))}</span></div>`;
                    return;
                }
                grid.innerHTML = items.map(item => {
                    const state = item.state || (item.enabled ? 'waiting' : 'disabled');
                    const enabledText = item.enabled ? tx('enabled') : tx('disabled');
                    const age = (typeof item.age_sec === 'number' && item.state !== 'disabled') ? ` · ${item.age_sec}s ago` : '';
                    const msg = item.message ? `${safe(localizedMessage(item.message))}${age}` : (item.enabled ? `${safe(tx('waitingTrigger'))}${age}` : safe(tx('notEnabled')));
                    return `<div class="push-card">
                        <div class="push-name">${safe(channelName(item.key, item.label_en))}</div>
                        <div class="push-enabled">${enabledText}</div>
                        <span class="push-chip ${safe(state)}">${stateLabel[state] || stateLabel.waiting}</span>
                        <div class="push-message" title="${safe(msg)}">${msg}</div>
                    </div>`;
                }).join('');
            }

            function renderRows(results){
                const tbody = document.getElementById('results-body');
                const membership = document.getElementById('membership_status')?.value || 'member';
                const safe = (s) => String(s || '').replace(/[&<>"']/g, (m) => ({
                    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
                }[m]));
                const hotelNameHtml = (r) => {
                    const primary = r.name_primary || r.name_zh || '';
                    const en = r.name_en || r.name || '(Hotel name not found)';
                    const inner = safe(bilingualText(primary, en));
                    return `<a href="${safe(r.url)}" target="_blank">${inner}</a>`;
                };
                const roomTitleZh = (title) => {
                    const lang = document.getElementById('primary_language')?.value || 'zh_cn';
                    const t = String(title || '').toLowerCase();
                    let key = '';
                    if (t.includes('economy') && t.includes('single')) key = 'economy_single';
                    else if (t.includes('single')) key = 'single';
                    else if (t.includes('economy') && t.includes('double')) key = 'economy_double';
                    else if (t.includes('double')) key = 'double';
                    else if (t.includes('economy') && t.includes('twin')) key = 'economy_twin';
                    else if (t.includes('twin')) key = 'twin';
                    else if (t.includes('heartful') || t.includes('accessible')) key = 'accessible';
                    const labels = {
                      zh_cn: {economy_single:'经济单人房', single:'单人房', economy_double:'经济大床房', double:'大床房', economy_twin:'经济双床房', twin:'双床房', accessible:'无障碍房'},
                      zh_tw: {economy_single:'經濟單人房', single:'單人房', economy_double:'經濟雙人床房', double:'雙人床房', economy_twin:'經濟雙床房', twin:'雙床房', accessible:'無障礙房'},
                      ja: {economy_single:'エコノミーシングル', single:'シングル', economy_double:'エコノミーダブル', double:'ダブル', economy_twin:'エコノミーツイン', twin:'ツイン', accessible:'ハートフルルーム'},
                      ko: {economy_single:'이코노미 싱글', single:'싱글', economy_double:'이코노미 더블', double:'더블', economy_twin:'이코노미 트윈', twin:'트윈', accessible:'배리어프리룸'}
                    };
                    if (key) return (labels[lang] || labels.zh_cn)[key] || '';
                    return '';
                };
                const roomSmokingLabel = (title, parsedSmoking) => {
                    if (parsedSmoking === 'smoking') return ' 🚬';
                    if (parsedSmoking === 'non_smoking') return ' 🚭';
                    const raw = String(title || '');
                    const t = raw.toLowerCase();
                    if (t.includes('non-smoking') || t.includes('non smoking') || t.includes('nonsmoking') || t.includes('no smoking') || raw.includes('禁煙') || raw.includes('禁烟')) {
                        return ' 🚭';
                    }
                    if (t.includes('smoking') || raw.includes('喫煙') || raw.includes('吸烟')) {
                        return ' 🚬';
                    }
                    const selectedSmoking = document.getElementById('smoking')?.value || 'all';
                    if (selectedSmoking === 'Smoking') return ' 🚬';
                    if (selectedSmoking === 'noSmoking') return ' 🚭';
                    return '';
                };
                const priceHtmlFor = (nonMemberText, memberText) => {
                    if (membership === 'member') return memberText ? `${safe(memberText)}<div>${safe(tx('memberPrice'))}</div>` : `${safe(nonMemberText || '-')}<div>${safe(tx('memberPriceUnknown'))}</div>`;
                    if (membership === 'non_member') return `${safe(nonMemberText || '-')}<div>${safe(tx('nonMemberPrice'))}</div>`;
                    let out = `${safe(nonMemberText || '-')}`;
                    if (memberText) out += `<div>${safe(tx('memberPrice'))}: ${safe(memberText)}</div>`;
                    return out;
                };
                const roomHtmlFor = (roomEn, roomZh, url, parsedSmoking) => {
                    if (!roomEn || String(roomEn).trim() === '-') return '-';
                    const zh = roomZh || roomTitleZh(roomEn);
                    const en = roomEn;
                    const smoke = roomSmokingLabel(roomEn, parsedSmoking);
                    const label = `${safe(bilingualText(zh, en))}${safe(smoke)}`;
                    return `<a href="${safe(url || '#')}" target="_blank">${label}</a>`;
                };
                setResultStats(results);
                if (!Array.isArray(results) || results.length === 0){
                    tbody.innerHTML = `<tr><td colspan="6" class="empty-results">${safe(tx('noData'))}</td></tr>`;
                    return;
                }

                const rows = [];

                results.forEach(r => {
                    const nameHtml  = hotelNameHtml(r);

                    // 生成一行的帮助函数：是否显示Code/Name由首行决定
                    const addRow = (showCode, showName, status, priceHtml, leftHtml, roomHtml) => {
                        const info = statusInfo(r, status);
                        const statusHtml = status ? `<span class="status-badge ${info.cls}">${status} ${info.label}</span>` : '';
                        rows.push(
                            `<tr class="${info.row}">
                              <td class="code-cell">${showCode ? safe(r.code) : ''}</td>
                              <td class="hotel-cell">${showName ? nameHtml : ''}</td>
                              <td>${statusHtml}</td>
                              <td class="price-cell">${priceHtml}</td>
                              <td class="center-cell">${safe(leftHtml)}</td>
                              <td>${roomHtml}</td>
                            </tr>`
                        );
                    };

                    // 情况 A：要求的房型不存在 → 只渲染一行，显示❗，其余列为 "-"
                    if (r.requirement_unmet){
                        addRow(true, true, '❗', '-', '-', '-');
                        return;
                    }

                    // 情况 B：后端提供了符合条件的房型列表 → 每个房型单独一行
                    if (Array.isArray(r.offers_display) && r.offers_display.length > 0){
                        r.offers_display.forEach((o, idx) => {
                            const price = priceHtmlFor(o.price_text, o.member_price_text);
                            const left = o.remaining_norm || '-';
                            const room = roomHtmlFor(o.room_title, o.room_title_primary || '', r.url, o.room_smoking || '');
                            const st   = (idx === 0 ? '✅' : '');
                            addRow(idx === 0, idx === 0, st, price, left, room);
                        });
                        return;
                    }

                    // 情况 C：回退到单值字段（兼容旧结构）
                    const status = (r.available === true ? '✅' : (r.available === false ? '❌' : '❓'));
                    const price = priceHtmlFor(r.min_price_text, r.min_member_price_text);
                    const left = r.min_remaining   || '-';
                    const room = roomHtmlFor(r.min_price_room, '', r.url);
                    addRow(true, true, status, price, left, room);
                });

                tbody.innerHTML = rows.join('');
            }

            function hms(seconds){
              if (seconds == null || !Number.isFinite(Number(seconds))) return '-';
              let s = Math.max(0, Math.floor(Number(seconds)));
              const h = Math.floor(s / 3600); s %= 3600;
              const m = Math.floor(s / 60); s %= 60;
              return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
            }

            function renderAvailabilityLogs(logs){
              const tbody = document.getElementById('availability-log-body');
              if (!tbody) return;
              const safe = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (m) => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
              }[m]));
              if (!Array.isArray(logs) || logs.length === 0){
                tbody.innerHTML = `<tr><td colspan="6" class="empty-results">${safe(tx('noLog'))}</td></tr>`;
                return;
              }
              tbody.innerHTML = logs.map(item => {
                const active = item.disappeared_ts == null;
                const hotel = item.url ? `<a href="${safe(item.url)}" target="_blank">${safe(item.hotel || '-')}</a>` : safe(item.hotel || '-');
                return `<tr class="${active ? 'row-available' : ''}">
                  <td class="code-cell">${safe(item.code || '-')}</td>
                  <td class="hotel-cell">${hotel}</td>
                  <td>${safe(item.appeared_at || '-')}</td>
                  <td>${active ? '-' : safe(hms(item.duration_sec))}</td>
                  <td class="price-cell">${safe(item.price || '-')}</td>
                  <td>${safe(item.room_type || '-')}</td>
                </tr>`;
              }).join('');
            }

            async function refreshStatus(){
              try{
                const r = await fetch('/status');
                const j = await r.json();
                setRunning(!!j.running);
                renderProgress(j.progress);
                if (j && j.config){
                  setIfNotFocused('start_date', j.config.start_date);
                  setIfNotFocused('end_date', j.config.end_date);
                  setIfNotFocused('people', j.config.people);
                  setIfNotFocused('rooms', j.config.rooms);
                  setIfNotFocused('smoking', j.config.smoking);
                  setIfNotFocused('room_requirement', (j.config.room_requirement || j.config.om_requirement || 'any'));
                  setIfNotFocused('membership_status', j.config.membership_status || 'member');
                  setIfNotFocused('primary_language', j.config.primary_language || 'zh_cn');
                  setIfNotFocused('engine', j.config.engine || 'http');
                  setIfNotFocused('smart_parallel_workers', j.config.smart_parallel_workers || 1);
                  const elParallel = document.getElementById('smart_parallel_enabled');
                  if (elParallel && !recentlyEdited('smart_parallel_enabled') && !BLOCK_REMOTE_OVERWRITE) elParallel.checked = !!j.config.smart_parallel_enabled;

                  const elLocal = document.getElementById('enable_local');
                  if (elLocal && !recentlyEdited('enable_local') && !BLOCK_REMOTE_OVERWRITE) elLocal.checked = !!j.config.enable_local;

                  const elEmail = document.getElementById('enable_email');
                  if (elEmail && !recentlyEdited('enable_email') && !BLOCK_REMOTE_OVERWRITE) elEmail.checked = !!j.config.enable_email;

                  const elTg = document.getElementById('enable_telegram');
                  if (elTg && !recentlyEdited('enable_telegram') && !BLOCK_REMOTE_OVERWRITE) elTg.checked = !!j.config.enable_telegram;
                  const elBark = document.getElementById('enable_bark');
                  if (elBark && !recentlyEdited('enable_bark') && !BLOCK_REMOTE_OVERWRITE) elBark.checked = !!j.config.enable_bark;
                  const elBarkCritical = document.getElementById('bark_critical_enabled');
                  if (elBarkCritical && !recentlyEdited('bark_critical_enabled') && !BLOCK_REMOTE_OVERWRITE) elBarkCritical.checked = !!j.config.bark_critical_enabled;
                  const elServerChan = document.getElementById('enable_serverchan');
                  if (elServerChan && !recentlyEdited('enable_serverchan') && !BLOCK_REMOTE_OVERWRITE) elServerChan.checked = !!j.config.enable_serverchan;
                  ['notify_available','notify_unavailable','notify_availability_count_change','notify_start','notify_stop','notify_search_error'].forEach(id => {
                    const el = document.getElementById(id);
                    if (el && !recentlyEdited(id) && !BLOCK_REMOTE_OVERWRITE && id in j.config) el.checked = !!j.config[id];
                  });

                  setIfNotFocused('smtp_host', j.config.smtp_host);
                  if ('smtp_port' in j.config) setIfNotFocused('smtp_port', j.config.smtp_port);
                  const elTls = document.getElementById('smtp_tls');
                  if (elTls && !recentlyEdited('smtp_tls') && !BLOCK_REMOTE_OVERWRITE) elTls.checked = !!j.config.smtp_tls;
                  setIfNotFocused('smtp_user', j.config.smtp_user);
                  setIfNotFocused('email_from', j.config.email_from);
                  setIfNotFocused('email_to', j.config.email_to);

                  setIfNotFocused('bot_token', j.config.bot_token);
                  setIfNotFocused('chat_id', j.config.chat_id);
                  setIfNotFocused('bark_key', j.config.bark_key);
                  setIfNotFocused('bark_server', j.config.bark_server || 'https://api.day.app');
                  if ('bark_critical_volume' in j.config) setIfNotFocused('bark_critical_volume', j.config.bark_critical_volume);
                  setIfNotFocused('bark_critical_sound', j.config.bark_critical_sound || 'alarm');
                  setIfNotFocused('serverchan_sendkey', j.config.serverchan_sendkey);

                  if ('available_alert_repeat' in j.config) setIfNotFocused('alert_repeat', j.config.available_alert_repeat);
                  if ('available_alert_repeat_interval_sec' in j.config) setIfNotFocused('alert_interval', j.config.available_alert_repeat_interval_sec);
                  if ('loop_interval_seconds' in j.config) setIfNotFocused('loop_interval', j.config.loop_interval_seconds);
                  if ('per_hotel_delay_seconds' in j.config) setIfNotFocused('per_hotel_delay', j.config.per_hotel_delay_seconds);
                  if ('request_jitter_percent' in j.config) setIfNotFocused('request_jitter', j.config.request_jitter_percent);
                  if ('radius_query' in j.config) setIfNotFocused('radius_query', j.config.radius_query || '');
                  if ('radius_lat' in j.config) setIfNotFocused('radius_lat', j.config.radius_lat || '');
                  if ('radius_lng' in j.config) setIfNotFocused('radius_lng', j.config.radius_lng || '');
                  if ('radius_km' in j.config) setIfNotFocused('radius_km', j.config.radius_km || 5);
                  // keep numeric displays in sync
                  syncDisplayValues();
                  restoreAreaFromConfig(j.config);

                renderSummary(j.config);
              }
                renderRows(j.results || []);
                renderAvailabilityLogs(j.availability_logs || []);
                renderPushStatus(j.notification_status || []);
                const act = (j && j.action) ? j.action : '(idle)';
                const age = (j && (typeof j.action_age_sec === 'number')) ? j.action_age_sec : null;
                const actLine = `${tx('currentAction')}: ${act}${age!=null ? ` (${age}s ago)` : ''}`;
                const actEl = document.getElementById('action-text');
                if (actEl) actEl.textContent = actLine;
              }catch(e){
                // ignore
              }
            }

            function setIfNotFocused(id, value){
              if (value === undefined) return;
              if (BLOCK_REMOTE_OVERWRITE) return;
              const el = document.getElementById(id);
              if(!el) return;
              if(document.activeElement === el) return;
              if(recentlyEdited(id)) return;
              if (id === 'smtp_pass') return;
              el.value = value;
            }

            document.getElementById('btn_start').addEventListener('click', (e)=>{e.preventDefault(); callStart();});
            document.getElementById('btn_stop').addEventListener('click', (e)=>{e.preventDefault(); callStop();});
            document.getElementById('btn_today').addEventListener('click', (e)=>{e.preventDefault(); setDateRange(new Date(), 1);});
            document.getElementById('btn_tomorrow').addEventListener('click', (e)=>{e.preventDefault(); const d=new Date(); d.setDate(d.getDate()+1); setDateRange(d, 1);});
            document.getElementById('btn_weekend').addEventListener('click', (e)=>{e.preventDefault(); setNextWeekend();});
            document.getElementById('btn_history_refresh').addEventListener('click', (e)=>{e.preventDefault(); refreshSearchHistory();});
            document.getElementById('btn_history_clear').addEventListener('click', (e)=>{e.preventDefault(); clearSearchHistory();});
            document.getElementById('btn_local_test').addEventListener('click', (e)=>{e.preventDefault(); callLocalTest();});
            const barkTestButton = document.getElementById('btn_bark_test');
            if (barkTestButton) barkTestButton.addEventListener('click', (e)=>{e.preventDefault(); callBarkTest();});
            const barkSoundButton = document.getElementById('btn_bark_sound_test');
            if (barkSoundButton) barkSoundButton.addEventListener('click', (e)=>{e.preventDefault(); callBarkSoundTest();});
            const upgradeButton = document.getElementById('btn_upgrade');
            if (upgradeButton) upgradeButton.addEventListener('click', (e)=>{e.preventDefault(); callUpgrade();});
            const barkKeyInput = document.getElementById('bark_key');
            if (barkKeyInput) barkKeyInput.addEventListener('input', ()=>{
              if ((barkKeyInput.value || '').trim().length > 48) validateBarkKeyInput();
            });
            const areaRegion = document.getElementById('area_region');
            if (areaRegion) areaRegion.addEventListener('change', populateAreaDetails);
	            const areaDetail = document.getElementById('area_detail');
	            if (areaDetail) areaDetail.addEventListener('change', ()=>{ AREA_HOTELS = []; AREA_SELECTED_CODES = null; renderAreaHotels(); });
            const areaFilter = document.getElementById('area_filter');
            if (areaFilter) areaFilter.addEventListener('input', renderAreaHotels);
            document.querySelectorAll('input[name="hotel_picker_mode"]').forEach(el => {
              el.addEventListener('change', () => {
	                setPickerMode(currentSearchMode());
	                AREA_HOTELS = [];
	                AREA_SELECTED_CODES = null;
	                renderAreaHotels();
                BLOCK_REMOTE_OVERWRITE = true;
              });
            });
            const primaryLanguage = document.getElementById('primary_language');
            if (primaryLanguage) primaryLanguage.addEventListener('change', ()=>{
              applyUiLanguage();
              renderAreaHotels();
              if (currentSearchMode() === 'area' && document.getElementById('area_region')?.value) loadAreaHotels();
            });
            const btnAreaLoad = document.getElementById('btn_area_load');
            if (btnAreaLoad) btnAreaLoad.addEventListener('click', (e)=>{ e.preventDefault(); loadAreaHotels(); });
            const btnRadiusLoad = document.getElementById('btn_radius_load');
            if (btnRadiusLoad) btnRadiusLoad.addEventListener('click', (e)=>{ e.preventDefault(); loadRadiusHotels(); });
            const btnAreaAll = document.getElementById('btn_area_all');
            if (btnAreaAll) btnAreaAll.addEventListener('click', (e)=>{ e.preventDefault(); setAreaHotelChecks(true); });
            const btnAreaNone = document.getElementById('btn_area_none');
            if (btnAreaNone) btnAreaNone.addEventListener('click', (e)=>{ e.preventDefault(); setAreaHotelChecks(false); });
            document.getElementById('btn_default').addEventListener('click', (e)=>{e.preventDefault();
              // 恢复默认（不会立刻写磁盘）
              document.getElementById('start_date').value = todayStr();
              document.getElementById('end_date').value   = plusOneDayStr();
              document.getElementById('people').value     = 1;
              document.getElementById('rooms').value      = 1;
              document.getElementById('smoking').value    = 'all';
              document.getElementById('room_requirement').value = 'any';
              document.getElementById('membership_status').value = 'member';
              const langEl = document.getElementById('primary_language');
              if (langEl) langEl.value = 'zh_cn';
              applyUiLanguage();
              const engineEl = document.getElementById('engine');
              if (engineEl) engineEl.value = 'http';
	              AREA_HOTELS = [];
	              AREA_SELECTED_CODES = null;
	              renderAreaHotels();
              ['enable_telegram','enable_local','enable_email','enable_bark','enable_serverchan','smart_parallel_enabled','bark_critical_enabled'].forEach(id=>{
                const c = document.getElementById(id); if (c) c.checked = false;
              });
              ['notify_available','notify_unavailable','notify_availability_count_change','notify_start','notify_stop'].forEach(id=>{
                const c = document.getElementById(id); if (c) c.checked = true;
              });
              const notifyErr = document.getElementById('notify_search_error');
              if (notifyErr) notifyErr.checked = false;
              ['bot_token','chat_id','smtp_host','smtp_port','smtp_user','smtp_pass','email_from','email_to','bark_key','bark_critical_sound','serverchan_sendkey']
                .forEach(id=>{ const el=document.getElementById(id); if (el) el.value=''; });
              document.getElementById('bark_server').value = 'https://api.day.app';
              document.getElementById('loop_interval').value = 30;
              document.getElementById('per_hotel_delay').value = 1;
              document.getElementById('request_jitter').value = 40;
              document.getElementById('smart_parallel_workers').value = 1;
              const barkCriticalVolume = document.getElementById('bark_critical_volume');
              if (barkCriticalVolume) barkCriticalVolume.value = 5;
              document.getElementById('alert_repeat').value = 0;
              document.getElementById('alert_interval').value = 300;
              document.getElementById('radius_query').value = '';
              document.getElementById('radius_lat').value = '';
              document.getElementById('radius_lng').value = '';
              document.getElementById('radius_km').value = 5;
              setPickerMode('area');
              syncDisplayValues();
              BLOCK_REMOTE_OVERWRITE = true;
            });
            initAnimatedDetails();
            refreshStatus();
            refreshSearchHistory();
            refreshUpdateStatus();
            setInterval(refreshStatus, 2000);
            setInterval(refreshUpdateStatus, 10000);
