            // 防止 /status 覆盖用户正在编辑的表单
            let BLOCK_REMOTE_OVERWRITE = false;
            const EDIT_TS = {};
            let PROGRESS_ANIM_FRAME = null;
            let LAST_PROGRESS_STATE = null;
            let LAST_RUNNING = false;
            let LAST_RESULTS = [];
            let RESULT_FILTER = 'all';
            let RESULT_SORT = 'default';
            let RESULT_QUERY = '';
            let RESULT_CHANGED_CODES = new Set();
            const RESULT_VIEW_PREFS_KEY = 'toyoko-chan-result-view-v1';
            let FORM_DIRTY = false;
            let LAST_RESULTS_FINGERPRINT = '';
            let RESULT_CHANGE_CLASSES = new Map();
            let RESULT_CHANGE_TOKEN = 0;
            let STATUS_REFRESH_IN_FLIGHT = false;
            let STATUS_FAILURES = 0;
            let STATUS_RECONNECT_TIMER = null;
            let STATUS_BOOTSTRAPPED = false;
            let SERVER_INSTANCE_ID = '';
            let RESULTS_REVISION = -1;
            let AVAILABILITY_LOGS_REVISION = -1;
            let CATALOG_REFRESH_IN_FLIGHT = false;
            let CONNECTION_ONLINE = true;
            let LAST_STATUS_UPDATED_AT = null;
            const HOTEL_INFO_CACHE = new Map();
            const HOTEL_INFO_REQUESTS = new Map();
            let HOTEL_INFO_SHOW_TIMER = null;
            let HOTEL_INFO_HIDE_TIMER = null;
            let ACTIVE_HOTEL_INFO_TRIGGER = null;
            let HOTEL_INFO_MAP = null;
            let LAST_CATALOG_STATUS = null;
            let LAST_PROVIDER_CATALOG_STATUS = null;
            let LAST_PROVIDER_HEALTH = {};
            let LAST_DIAGNOSTICS = {};
            let LAST_MOBILE_ACCESS_STATUS = null;
            let PWA_INSTALL_PROMPT = null;
            let LAST_TREND_REFRESH = 0;
            let LAST_TREND_DATA = null;
            let LAST_HOME_REFRESH = 0;
            let LAST_HOME_PAYLOAD = null;
            let LAST_CONFIG = {};
            let PREFERENCE_SAVE_TIMER = null;
            let PREFERENCE_SAVE_IN_FLIGHT = false;
            let PREFERENCE_SAVE_QUEUED = false;
            const OFFLINE_RESULTS_KEY = 'toyoko-chan-offline-results-v1';
            let MOBILE_CONNECTION_MODE = localStorage.getItem('toyoko-chan-mobile-connection-v1') || 'lan';
            const APP_VIEW_KEY = 'toyoko-chan-active-view-v1';
            const SIDEBAR_COLLAPSED_KEY = 'toyoko-chan-sidebar-collapsed-v1';
            const THEME_KEY = 'toyoko-chan-theme-v1';
            const LANGUAGE_KEY = 'toyoko-chan-language-v1';
            const GUIDE_SEEN_KEY = 'toyoko-chan-guide-seen-version';
            const APP_VIEWS = ['home', 'search', 'monitor', 'search-settings', 'push-settings', 'interface'];
            let ACTIVE_APP_VIEW = 'home';
            let THEME_PREFERENCE = 'system';
            let GUIDE_STEP = 0;
            let GUIDE_AUTO_OPEN = false;
            let UPDATE_DIALOG_AUTO_OPEN = false;
            let UPDATE_AUTO_PROMPTED_VERSION = '';
            function markEdited(id){ EDIT_TS[id] = Date.now(); setConfigDirty(true); }
            function recentlyEdited(id, ms=10000){ return EDIT_TS[id] && (Date.now() - EDIT_TS[id] < ms); }
            function setConfigDirty(dirty){
              FORM_DIRTY = !!dirty;
              const state = document.getElementById('dock-config-state');
              if (!state) return;
              state.textContent = tx(FORM_DIRTY ? 'configPending' : 'configReady');
              state.className = `config-state ${FORM_DIRTY ? 'dirty' : 'clean'}`;
            }
            function setConnectionOnline(online){
              CONNECTION_ONLINE = !!online;
              const state = document.getElementById('connection-state');
              if (state) {
                state.textContent = tx(online ? 'connectionOnline' : 'connectionOffline');
                state.className = `connection-state ${online ? 'online' : 'offline'}`;
              }
              const homeConnection = document.getElementById('home-health-connection');
              if (homeConnection) homeConnection.textContent = tx(online ? 'homeNormal' : 'connectionOffline');
              document.querySelector('.command-dock')?.classList.toggle('offline', !online);
            }
            function updateResultsTimestamp(){
              const element = document.getElementById('results_updated_at');
              if (!element) return;
              if (!LAST_STATUS_UPDATED_AT) {
                element.textContent = tx('neverUpdated');
                return;
              }
              const time = LAST_STATUS_UPDATED_AT.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});
              element.textContent = fmt('lastUpdated', {time});
              element.setAttribute('datetime', LAST_STATUS_UPDATED_AT.toISOString());
            }
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
                areaHint: '选择大区域；详细区域可不选，默认加载整个大区域。勾选酒店后直接点击启动。',
                areaSelected: '已选择大区域；可直接加载全部，或选择详细区域。勾选酒店后直接点击启动。',
                selectRegion: '请选择 / Select Region', selectRegionFirst: '先选择大区域 / Select a region first',
                filterPlaceholder: '按酒店名或编号过滤 / Filter by hotel name or code',
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
                smartParallelHelp: '仅 HTTP/API 生效；不同品牌并行，同品牌动态限速，重点与近期变化酒店优先',
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
                enableEmail: '启用邮件推送 / Enable Email', localHelp: '本地通知会调用系统工具：macOS 使用 terminal-notifier/osascript，Windows 使用 PowerShell，Linux 需要 notify-send。',
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
                tipSmartParallel: '仅 HTTP/API 生效。不同酒店品牌可错峰并行，同一品牌保持独立访问间隔；连续异常的品牌会短暂冷却，不影响其他品牌。默认 1 条，酒店较多时可提高到 2-3 条。',
                tipCadence: '每轮检索间隔控制两轮之间等待多久；每家酒店基础间隔控制同一检索线内访问频率；随机抖动会让间隔更自然。更稳妥的配置是每轮 120 秒以上、单店 2-5 秒并保留 30-50% 抖动。',
                tipReminder: '控制发现空房后的重复提醒。重复提醒次数为首次提醒后的追加提醒次数；最右侧 INF 表示持续提醒。冷却时间用于避免同一酒店短时间反复推送，建议 300 秒以上。',
                tipBark: '适合 iPhone/iPad。步骤：1. iPhone/iPad 安装 Bark App。2. 复制 App 首页的 Device Key。3. 填入 Bark Key。4. 公共服务保持默认 Bark Server；自建服务则填你的服务器地址。5. 勾选启用后启动搜索。',
                tipServerChan: '适合微信推送。步骤：1. 打开 Server 酱官网并用微信登录。2. 绑定微信推送通道。3. 在 SendKey 页面复制 SCT 开头的 SendKey。4. 粘贴到这里。5. 勾选启用后启动搜索。',
                tipTelegram: '步骤：1. 在 Telegram 搜索 BotFather。2. 使用 /newbot 创建机器人并复制 Bot Token。3. 给机器人发一条消息，或把机器人加入群组。4. 获取 Chat ID 后填入。5. 勾选启用后启动搜索。',
                tipLocal: '在本机弹出系统通知。步骤：1. 勾选启用本地通知。2. 点击发送测试通知。3. macOS 检查通知权限；Windows 需要 PowerShell；Linux 需要 notify-send 和图形桌面会话。4. 测试成功后启动搜索。',
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
                areaHint: '選擇大區域；詳細區域可不選，預設載入整個大區域。勾選飯店後直接點啟動。',
                areaSelected: '已選擇大區域；可直接載入全部，或選擇詳細區域。勾選飯店後直接點啟動。',
                selectRegion: '請選擇 / Select Region', selectRegionFirst: '先選擇大區域 / Select a region first',
                filterPlaceholder: '依飯店名稱或編號篩選 / Filter by hotel name or code',
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
                smartParallelHelp: '僅 HTTP/API 生效；不同品牌並行，同品牌動態限速，重點與近期變化飯店優先',
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
                enableEmail: '啟用郵件推送 / Enable Email', localHelp: '本地通知會使用系統工具：macOS 使用 terminal-notifier/osascript，Windows 使用 PowerShell，Linux 需要 notify-send。',
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
                tipSmartParallel: '僅 HTTP/API 生效。不同飯店品牌可錯峰並行，同一品牌維持獨立存取間隔；連續異常的品牌會短暫冷卻，不影響其他品牌。預設 1 條，飯店較多時可提高到 2-3 條。',
                tipCadence: '每輪搜尋間隔控制兩輪之間等待多久；每家飯店基礎間隔控制同一搜尋線內訪問頻率；隨機抖動會讓間隔更自然。',
                tipReminder: '控制發現空房後的重複提醒。重複提醒次數為首次提醒後的追加提醒次數；最右側 INF 表示持續提醒。冷卻時間建議 300 秒以上。',
                tipBark: '適合 iPhone/iPad。步驟：1. 安裝 Bark App。2. 複製 Device Key。3. 填入 Bark Key。4. 公共服務保持預設 Bark Server；自建服務則填你的伺服器地址。',
                tipServerChan: '適合微信推送。步驟：1. 打開 ServerChan 官網並登入。2. 綁定微信推送通道。3. 複製 SendKey。4. 貼到這裡。5. 勾選啟用後啟動搜尋。',
                tipTelegram: '步驟：1. 在 Telegram 搜尋 BotFather。2. 使用 /newbot 建立機器人並複製 Bot Token。3. 給機器人發訊息或加入群組。4. 取得 Chat ID 後填入。',
                tipLocal: '在本機彈出系統通知。步驟：1. 啟用本地通知。2. 傳送測試通知。3. macOS 檢查通知權限；Windows 需要 PowerShell；Linux 需要 notify-send 與圖形桌面工作階段。',
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
                areaHint: '大エリアを選択してください。詳細エリアは任意です。ホテルを選んで開始を押すと検索します。',
                areaSelected: '大エリアを選択済みです。全体を読み込むか、詳細エリアを選択できます。',
                selectRegion: '選択してください / Select Region', selectRegionFirst: '先に大エリアを選択 / Select a region first',
                filterPlaceholder: 'ホテル名または番号で絞り込み / Filter by hotel name or code',
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
                smartParallelHelp: 'HTTP/API のみ有効。ブランド別に動的制限し、重点・変化ホテルを優先します',
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
                enableEmail: 'メール通知を有効化 / Enable Email', localHelp: 'ローカル通知は macOS の terminal-notifier/osascript、Windows の PowerShell、Linux の notify-send を使用します。',
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
                tipSmartParallel: 'HTTP/API のみ有効です。異なるブランドは時間をずらして並列処理し、同一ブランドは独立した間隔を維持します。連続エラーのブランドだけを一時待機させます。',
                tipCadence: 'ラウンド間隔は次の検索までの待ち時間です。ホテルごとの基本間隔は同じライン内のアクセス頻度です。ランダム揺らぎで間隔を自然にします。',
                tipReminder: '空室発見後の繰り返し通知を制御します。回数は初回通知後の追加通知回数です。右端の INF は継続通知を意味します。クールダウンは 300 秒以上を推奨します。',
                tipBark: 'iPhone/iPad 向けです。手順：1. Bark App をインストール。2. Device Key をコピー。3. Bark Key に入力。4. 公開サービスは既定の Bark Server、自前サーバーはその URL を入力。',
                tipServerChan: 'WeChat 通知向けです。手順：1. ServerChan にログイン。2. 通知チャンネルを連携。3. SendKey をコピー。4. ここに貼り付け。5. 有効化して検索開始。',
                tipTelegram: '手順：1. Telegram で BotFather を検索。2. /newbot でボットを作成し Bot Token をコピー。3. ボットへメッセージを送るかグループに追加。4. Chat ID を入力。',
                tipLocal: 'この端末に通知を表示します。手順：1. ローカル通知を有効化。2. テスト通知を送信。3. macOS は通知権限、Windows は PowerShell、Linux は notify-send とデスクトップセッションを確認。',
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
                areaHint: '대지역을 선택하세요. 상세 지역은 선택하지 않아도 됩니다. 호텔을 선택한 뒤 시작을 누르면 검색합니다.',
                areaSelected: '대지역이 선택되었습니다. 전체를 불러오거나 상세 지역을 선택할 수 있습니다.',
                selectRegion: '선택하세요 / Select Region', selectRegionFirst: '먼저 대지역 선택 / Select a region first',
                filterPlaceholder: '호텔명 또는 번호로 필터 / Filter by hotel name or code',
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
                smartParallelHelp: 'HTTP/API 전용. 브랜드별 동적 제한과 중점·최근 변경 호텔 우선 처리',
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
                enableEmail: '이메일 푸시 활성화 / Enable Email', localHelp: '로컬 알림은 macOS의 terminal-notifier/osascript, Windows의 PowerShell, Linux의 notify-send를 사용합니다.',
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
                tipSmartParallel: 'HTTP/API에서만 작동합니다. 서로 다른 브랜드는 시차를 두고 병렬 처리하며 같은 브랜드는 독립적인 요청 간격을 유지합니다. 연속 오류 브랜드만 잠시 대기합니다.',
                tipCadence: '라운드 간격은 다음 검색까지의 대기 시간입니다. 호텔별 기본 간격은 같은 라인 안의 접근 빈도입니다. 랜덤 지터로 간격을 더 자연스럽게 만듭니다.',
                tipReminder: '빈 객실 발견 후 반복 알림을 제어합니다. 횟수는 첫 알림 이후 추가 알림 횟수입니다. 오른쪽 INF는 계속 알림을 의미합니다. 쿨다운은 300초 이상을 권장합니다.',
                tipBark: 'iPhone/iPad용입니다. 단계: 1. Bark App 설치. 2. Device Key 복사. 3. Bark Key 입력. 4. 공용 서비스는 기본 Bark Server 유지, 자체 서버는 해당 URL 입력.',
                tipServerChan: 'WeChat 푸시용입니다. 단계: 1. ServerChan 로그인. 2. 푸시 채널 연결. 3. SendKey 복사. 4. 여기에 붙여넣기. 5. 활성화 후 검색 시작.',
                tipTelegram: '단계: 1. Telegram에서 BotFather 검색. 2. /newbot으로 봇 생성 후 Bot Token 복사. 3. 봇에 메시지를 보내거나 그룹에 추가. 4. Chat ID 입력.',
                tipLocal: '이 기기에 알림을 표시합니다. 단계: 1. 로컬 알림 활성화. 2. 테스트 전송. 3. macOS는 알림 권한, Windows는 PowerShell, Linux는 notify-send와 데스크톱 세션을 확인하세요.',
                tipEmail: 'SMTP로 이메일을 보냅니다. 단계: 1. 메일 서비스에서 SMTP 활성화. 2. 앱 비밀번호 생성. 3. SMTP Host, Port, Username, Password 입력. 4. From과 To 입력.'
              }
            };
            const UI18N_EXTRA = {
              zh_cn: {
                navSearch: '空房检索 / Vacancy Search', navMonitor: '空房监控 / Vacancy Monitor', interfaceSettings: '界面设定 / Interface Settings',
                collapseNav: '收起导航 / Collapse navigation', expandNav: '展开导航 / Expand navigation',
                guideOpen: '使用向导 / Guide', guideClose: '关闭向导 / Close guide', guideTitle: '东横酱使用向导 / Toyoko Chan Guide',
                guideSkip: '稍后 / Skip', guideBack: '上一步 / Back', guideNext: '下一步 / Next', guideFinish: '完成 / Finish', guideProgress: '向导进度 / Guide progress',
                guideStep1Title: '认识界面 / Interface Overview', guideStep1Body: '使用左侧导航切换工作区；顶部操作条始终提供单次检索、启动和停止。 / Use the sidebar to switch workspaces; the top command bar keeps scan, start, and stop within reach.', guideStep1Tip: '提示：启动后会自动进入空房监控。 / Tip: Starting a scan automatically opens Vacancy Monitor.',
                guideStep2Title: '搜索酒店 / Find Hotels', guideStep2Body: '先设定日期、人数、房型和会员状态，再选择酒店品牌。通过区域或方圆模式加载酒店，并勾选需要检索的对象。 / Set dates, guests, room and membership first, then choose brands. Load hotels by area or radius and check the hotels to scan.', guideStep2Tip: '提示：酒店选择会随搜索记录保存，下次启动可自动恢复。 / Tip: Hotel selections are saved with search history and can be restored next time.',
                guideStep3Title: '查看空房结果 / Review Results', guideStep3Body: '空房监控会集中显示有房、无房和需确认状态，以及价格、剩余数量和房型。酒店名与房型可打开官网详情或预订页。 / Vacancy Monitor shows available, unavailable and check states with price, quantity and room type. Hotel and room links open official detail or booking pages.', guideStep3Tip: '提示：使用结果筛选、搜索和变化标签，可以快速找到最新变化。 / Tip: Filters, search and the Changes tab help surface the latest updates.',
                guideStep4Title: '搜索设定 / Search Settings', guideStep4Body: 'HTTP/API 适合日常轻量检索；智能并行用于较多酒店，检索节奏控制轮次、单店间隔和随机抖动。 / HTTP/API is the lightweight daily choice. Smart Parallel helps with larger lists, while Scan Cadence controls rounds, hotel delay and jitter.', guideStep4Tip: '建议：每轮 120 秒以上，并保留自适应退避，降低异常流量风险。 / Recommended: use 120+ second rounds and keep Adaptive Backoff enabled.',
                guideStep5Title: '推送设定 / Push Settings', guideStep5Body: '先选择需要提醒的事件，再启用 Bark、Server酱、Telegram、本地通知或邮件。每个渠道都可独立配置。 / Choose notification events, then enable Bark, Server Chan, Telegram, Local Notifications or Email. Each channel is configured independently.', guideStep5Tip: '提示：正式监控前先发送测试通知，确认设备和系统权限正常。 / Tip: Send a test notification before monitoring to verify the device and system permissions.',
                workspace: '空房追踪工作区 / Vacancy workspace', sidebarHotelCount: '{count} 家酒店 / {count} hotels',
                searchViewHelp: '设定住宿条件、酒店范围并开始检索。 / Set stay conditions, hotel scope, and start searching.',
                monitorViewHelp: '查看运行状态、空房结果与实时推送状态。 / Review live status, vacancy results, and notifications.',
                searchSettingsViewHelp: '调整检索引擎、并行策略与访问节奏。 / Tune the engine, parallel strategy, and scan cadence.',
                pushSettingsViewHelp: '选择提醒事件并配置通知渠道。 / Choose alert events and configure notification channels.',
                interfaceViewHelp: '选择主语言与显示主题；偏好仅保存在本机浏览器。 / Choose language and theme; preferences stay in this browser.',
                theme: '主题 / Theme', language: '语言 / Language', languageHelp: '主语言始终与英语对照显示。 / The primary language is always paired with English.',
                themeHelp: '可跟随系统，也可固定浅色或深色主题。 / Follow the system or choose a fixed light or dark theme.',
                themeSystem: '跟随系统 / System', themeLight: '浅色 / Light', themeDark: '深色 / Dark',
                areaMode: '区域模式 / Area', radiusMode: '方圆模式 / Radius',
                placeAddressCoordinates: '地名地址或者坐标 / Place, Address, or Coordinates',
                radius: '方圆半径 / Radius', loadNearby: '查找附近酒店 / Load Nearby',
                radiusHelp: '地址通过 OpenStreetMap/Nominatim 解析，并按上方已选择的酒店品牌检索。 / Addresses use OpenStreetMap/Nominatim and the hotel brands selected above.',
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
                updateOpen: '软件更新 / Software Update', updateClose: '关闭更新窗口 / Close update dialog',
                updateDialogTitle: '软件更新 / Software Update', updateDialogKicker: '版本与项目 / VERSION & PROJECT',
                currentVersionLabel: '当前版本 / Current Version', latestVersionLabel: '最新版本 / Latest Version',
                versionInformation: '版本信息 / Version Information',
                authorLabel: '作者 / Author', githubLabel: '源代码 / Source Code', checkAgain: '重新检查 / Check Again',
                checkingUpdate: '正在检查更新 / Checking for updates', checkingUpdateMessage: '正在后台连接 PyPI，不会影响空房检索。 / Contacting PyPI in the background without interrupting vacancy scans.',
                upToDate: '已是最新版 / Up to date', upToDateMessage: '当前安装版本已经是 PyPI 上的最新版本。 / The installed version is the latest version on PyPI.',
                updateAvailableDetail: '有新版本可用，可以立即在后台更新。 / A new version is available and can be installed in the background.',
                updateFailedTitle: '检查更新失败 / Update check failed', updateFailedMessage: '暂时无法取得最新版本信息，请稍后重新检查。 / Latest version information is unavailable. Try again later.',
                updateUnknown: '尚未检查 / Not checked yet',
                currentAction: '状态 / Current', memberPrice: '会员价 / Member', memberPriceUnknown: '会员价未知 / Member price unknown',
                nonMemberPrice: '非会员价 / Non-member', sentOk: '发送成功 / sent OK',
                terminalNotifierSentOk: 'terminal-notifier 发送成功 / terminal-notifier sent OK',
                osascriptSentOk: 'osascript 发送成功 / osascript sent OK',
                scanOnce: '单次检索 / Scan Once', scanningOnce: '单次检索已启动 / Single scan started.', restart: '重新启动 / Restart',
                dockNoHotels: '尚未选择酒店 / No hotels selected', dockSelected: '已选择 {count} 家酒店 / {count} hotels selected',
                selectedSummary: '已选 {selected} / {total} / Selected', invalidDates: '退房日期必须晚于入住日期。 / Check-out must be after check-in.',
                allFilter: '全部 / All', sort: '排序 / Sort', sortDefault: '默认 / Default', sortStatus: '状态 / Status', sortPrice: '价格 / Price', sortName: '酒店名 / Hotel', sortDistance: '距离 / Distance',
                showingResults: '显示 {shown} / {total} / Showing', noFilteredResults: '当前筛选没有结果 / No results match this filter',
                configReady: '配置已同步 / Configuration ready', configPending: '有尚未应用的修改 / Changes apply on next start',
                connectionOnline: '连接正常 / Connected', connectionOffline: '连接中断，正在重连 / Reconnecting',
                snapshotHotels: '酒店 / Hotels', resultBecameAvailable: '{count} 家酒店出现空房 / {count} hotel(s) became available',
                resultNoLongerAvailable: '{count} 家酒店已无房 / {count} hotel(s) no longer available',
                resultRoomCountChanged: '{count} 家酒店房量有变化 / Room count changed at {count} hotel(s)',
                changesFilter: '变化 / Changes', resultSearchPlaceholder: '搜索编号、酒店或房型 / Search code, hotel, or room',
                refreshResults: '刷新 / Refresh', exportResults: '导出 CSV / Export',
                lastUpdated: '更新于 {time} / Updated', neverUpdated: '尚未更新 / Never updated',
                exportNoResults: '当前视图没有可导出的结果。 / No visible results to export.',
                adaptiveBackoff: '启用自适应退避 / Adaptive Backoff',
                adaptiveBackoffHelp: '访问异常达到 50% 时自动把下一轮间隔提高到 2 倍，连续异常最多 4 倍；恢复正常后自动回落。 / Automatically slows the next round to 2x when checks fail at 50% or more, up to 4x for consecutive unhealthy rounds.',
                safety: '流量保护 / Safety', safetyNormal: '正常 / Normal',
                safetyBackoff: '退避 {multiplier}× · 异常 {ratio}% / Backoff',
                hotelInfo: '酒店信息 / Hotel Info', loadingHotelInfo: '正在加载官网信息 / Loading official information...',
                hotelInfoUnavailable: '官网信息暂时无法加载 / Official information is unavailable.',
                officialReference: '官方参考 / Official Reference', addressLabel: '地址 / Address', directionsLabel: '交通前往方式 / Directions',
                byTrain: '乘坐电车 / By train', byCar: '驾车 / By car', byPlane: '乘坐飞机 / By plane',
                openOfficial: '打开官网 / Open Official Page',
                catalogTitle: '东横酒店数据 / Toyoko Hotel Data', catalogChecking: '正在核对东横官网酒店清单 / Checking Toyoko hotel list',
                catalogFresh: '东横酒店数据已是最新 / Toyoko hotel data is current', catalogUpdated: '东横酒店数据已更新 / Toyoko hotel data updated',
                catalogFailed: '后台更新失败，继续使用原缓存 / Refresh failed; using the previous cache',
                catalogMeta: '日本营业酒店 {open} 家 · 坐标 {coords} 家 · {cache} · {checked}',
                catalogCacheFresh: '缓存有效 / Cache fresh', catalogCacheStale: '缓存已过期 / Cache expired',
                catalogNeverChecked: '尚未检查 / Never checked', catalogCheckedAt: '检查于 {time} / Checked',
                catalogUpcoming: '即将开业 {count} 家 / {count} upcoming: {hotels}',
                catalogNewTitle: '发现 {count} 家新开业酒店 / {count} newly opened hotel(s)',
                catalogRefresh: '刷新酒店数据 / Refresh', catalogAcknowledge: '知道了 / Dismiss',
                catalogRefreshQueued: '已在后台开始刷新 / Background refresh started',
                catalogUnresolved: '其中 {count} 家暂缺坐标 / {count} hotel(s) still need coordinates',
                hotelBrands: '酒店品牌 / Hotel Brands', toyokoProvider: '东横 / Toyoko Inn', routeinnProvider: '露樱 / Route Inn Hotels', dormyProvider: '多美迎 / Dormy Inn', mystaysProvider: 'MYSTAYS Hotel', daiwaProvider: '大和ROYNET / Daiwa Roynet',
                routeinnProviderNote: '露樱包含露樱、露樱Grandia、Grandvrio、ARK / Route Inn includes Route Inn, Grandia, Grandvrio, and ARK.',
                providerRequired: '请至少选择一个酒店品牌。 / Select at least one hotel brand.',
                quickDates: '快捷日期 / Quick Dates', allBrands: '全部品牌 / All brands', selectedOnly: '仅看已选 / Selected only',
                listView: '列表 / List', mapView: '地图 / Map', visibleHotels: '显示 {shown} / {total} 家酒店 / Showing {shown} of {total} hotels',
                sortCode: '编号 / Code', decreasePeople: '减少人数 / Decrease people', increasePeople: '增加人数 / Increase people',
                decreaseRooms: '减少房间 / Decrease rooms', increaseRooms: '增加房间 / Increase rooms',
                toyokoShort: '东横', routeinnShort: '露樱', dormyShort: '多美迎', mystaysShort: 'MYSTAYS', daiwaShort: '大和ROYNET', partialProviderFailure: '部分品牌加载失败 / Some brands failed to load'
              },
              zh_tw: {
                navSearch: '空房搜尋 / Vacancy Search', navMonitor: '空房監控 / Vacancy Monitor', interfaceSettings: '介面設定 / Interface Settings',
                collapseNav: '收合導覽 / Collapse navigation', expandNav: '展開導覽 / Expand navigation',
                guideOpen: '使用導覽 / Guide', guideClose: '關閉導覽 / Close guide', guideTitle: '東橫醬使用導覽 / Toyoko Chan Guide',
                guideSkip: '稍後 / Skip', guideBack: '上一步 / Back', guideNext: '下一步 / Next', guideFinish: '完成 / Finish', guideProgress: '導覽進度 / Guide progress',
                guideStep1Title: '認識介面 / Interface Overview', guideStep1Body: '使用左側導覽切換工作區；頂部操作列始終提供單次搜尋、啟動和停止。 / Use the sidebar to switch workspaces; the top command bar keeps scan, start, and stop within reach.', guideStep1Tip: '提示：啟動後會自動進入空房監控。 / Tip: Starting a scan automatically opens Vacancy Monitor.',
                guideStep2Title: '搜尋飯店 / Find Hotels', guideStep2Body: '先設定日期、人數、房型和會員狀態，再選擇飯店品牌。透過區域或方圓模式載入並勾選飯店。 / Set dates, guests, room and membership first, then choose brands. Load hotels by area or radius and check the hotels to scan.', guideStep2Tip: '提示：飯店選擇會隨搜尋記錄保存，下次可自動還原。 / Tip: Hotel selections are saved with search history and can be restored next time.',
                guideStep3Title: '查看空房結果 / Review Results', guideStep3Body: '空房監控會顯示有房、無房和需確認狀態，以及價格、剩餘數量和房型。飯店名與房型可開啟官網或預訂頁。 / Vacancy Monitor shows available, unavailable and check states with price, quantity and room type. Hotel and room links open official detail or booking pages.', guideStep3Tip: '提示：結果篩選、搜尋和變化標籤可快速找到最新變化。 / Tip: Filters, search and the Changes tab help surface the latest updates.',
                guideStep4Title: '搜尋設定 / Search Settings', guideStep4Body: 'HTTP/API 適合日常輕量搜尋；智慧並行用於較多飯店，搜尋節奏控制輪次、單店間隔與隨機抖動。 / HTTP/API is the lightweight daily choice. Smart Parallel helps with larger lists, while Scan Cadence controls rounds, hotel delay and jitter.', guideStep4Tip: '建議：每輪 120 秒以上，並保留自適應退避。 / Recommended: use 120+ second rounds and keep Adaptive Backoff enabled.',
                guideStep5Title: '推送設定 / Push Settings', guideStep5Body: '先選擇提醒事件，再啟用 Bark、Server醬、Telegram、本機通知或郵件。 / Choose notification events, then enable Bark, Server Chan, Telegram, Local Notifications or Email.', guideStep5Tip: '提示：正式監控前先發送測試通知。 / Tip: Send a test notification before monitoring to verify the device and system permissions.',
                workspace: '空房追蹤工作區 / Vacancy workspace', sidebarHotelCount: '{count} 家飯店 / {count} hotels',
                searchViewHelp: '設定住宿條件、飯店範圍並開始搜尋。 / Set stay conditions, hotel scope, and start searching.',
                monitorViewHelp: '查看執行狀態、空房結果與即時推送狀態。 / Review live status, vacancy results, and notifications.',
                searchSettingsViewHelp: '調整搜尋引擎、並行策略與存取節奏。 / Tune the engine, parallel strategy, and scan cadence.',
                pushSettingsViewHelp: '選擇提醒事件並設定通知管道。 / Choose alert events and configure notification channels.',
                interfaceViewHelp: '選擇主語言與顯示主題；偏好僅保存在本機瀏覽器。 / Choose language and theme; preferences stay in this browser.',
                theme: '主題 / Theme', language: '語言 / Language', languageHelp: '主語言始終與英語對照顯示。 / The primary language is always paired with English.',
                themeHelp: '可跟隨系統，也可固定淺色或深色主題。 / Follow the system or choose a fixed light or dark theme.',
                themeSystem: '跟隨系統 / System', themeLight: '淺色 / Light', themeDark: '深色 / Dark',
                areaMode: '區域模式 / Area', radiusMode: '方圓模式 / Radius',
                placeAddressCoordinates: '地名地址或者座標 / Place, Address, or Coordinates',
                radius: '方圓半徑 / Radius', loadNearby: '查找附近飯店 / Load Nearby',
                radiusHelp: '地址透過 OpenStreetMap/Nominatim 解析，並依上方選取的飯店品牌搜尋。 / Addresses use OpenStreetMap/Nominatim and the hotel brands selected above.',
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
                updateOpen: '軟體更新 / Software Update', updateClose: '關閉更新視窗 / Close update dialog',
                updateDialogTitle: '軟體更新 / Software Update', updateDialogKicker: '版本與專案 / VERSION & PROJECT',
                currentVersionLabel: '目前版本 / Current Version', latestVersionLabel: '最新版本 / Latest Version',
                versionInformation: '版本資訊 / Version Information',
                authorLabel: '作者 / Author', githubLabel: '原始碼 / Source Code', checkAgain: '重新檢查 / Check Again',
                checkingUpdate: '正在檢查更新 / Checking for updates', checkingUpdateMessage: '正在背景連線 PyPI，不會影響空房搜尋。 / Contacting PyPI in the background without interrupting vacancy scans.',
                upToDate: '已是最新版 / Up to date', upToDateMessage: '目前安裝版本已是 PyPI 上的最新版本。 / The installed version is the latest version on PyPI.',
                updateAvailableDetail: '有新版本可用，可以立即在背景更新。 / A new version is available and can be installed in the background.',
                updateFailedTitle: '檢查更新失敗 / Update check failed', updateFailedMessage: '暫時無法取得最新版本資訊，請稍後重新檢查。 / Latest version information is unavailable. Try again later.',
                updateUnknown: '尚未檢查 / Not checked yet',
                currentAction: '狀態 / Current', memberPrice: '會員價 / Member', memberPriceUnknown: '會員價未知 / Member price unknown',
                nonMemberPrice: '非會員價 / Non-member', sentOk: '傳送成功 / sent OK',
                terminalNotifierSentOk: 'terminal-notifier 傳送成功 / terminal-notifier sent OK',
                osascriptSentOk: 'osascript 傳送成功 / osascript sent OK',
                scanOnce: '單次搜尋 / Scan Once', scanningOnce: '單次搜尋已啟動 / Single scan started.', restart: '重新啟動 / Restart',
                dockNoHotels: '尚未選擇飯店 / No hotels selected', dockSelected: '已選擇 {count} 家飯店 / {count} hotels selected',
                selectedSummary: '已選 {selected} / {total} / Selected', invalidDates: '退房日期必須晚於入住日期。 / Check-out must be after check-in.',
                allFilter: '全部 / All', sort: '排序 / Sort', sortDefault: '預設 / Default', sortStatus: '狀態 / Status', sortPrice: '價格 / Price', sortName: '飯店名 / Hotel', sortDistance: '距離 / Distance',
                showingResults: '顯示 {shown} / {total} / Showing', noFilteredResults: '目前篩選沒有結果 / No results match this filter',
                configReady: '設定已同步 / Configuration ready', configPending: '有尚未套用的修改 / Changes apply on next start',
                connectionOnline: '連線正常 / Connected', connectionOffline: '連線中斷，正在重連 / Reconnecting',
                snapshotHotels: '飯店 / Hotels', resultBecameAvailable: '{count} 家飯店出現空房 / {count} hotel(s) became available',
                resultNoLongerAvailable: '{count} 家飯店已無房 / {count} hotel(s) no longer available',
                resultRoomCountChanged: '{count} 家飯店房量有變化 / Room count changed at {count} hotel(s)',
                changesFilter: '變化 / Changes', resultSearchPlaceholder: '搜尋編號、飯店或房型 / Search code, hotel, or room',
                refreshResults: '重新整理 / Refresh', exportResults: '匯出 CSV / Export',
                lastUpdated: '更新於 {time} / Updated', neverUpdated: '尚未更新 / Never updated',
                exportNoResults: '目前檢視沒有可匯出的結果。 / No visible results to export.',
                adaptiveBackoff: '啟用自適應退避 / Adaptive Backoff',
                adaptiveBackoffHelp: '存取異常達到 50% 時，自動把下一輪間隔提高到 2 倍；連續異常最多 4 倍，恢復正常後自動回落。 / Automatically slows the next round to 2x when checks fail at 50% or more, up to 4x for consecutive unhealthy rounds.',
                safety: '流量保護 / Safety', safetyNormal: '正常 / Normal',
                safetyBackoff: '退避 {multiplier}× · 異常 {ratio}% / Backoff',
                hotelInfo: '飯店資訊 / Hotel Info', loadingHotelInfo: '正在載入官網資訊 / Loading official information...',
                hotelInfoUnavailable: '官網資訊暫時無法載入 / Official information is unavailable.',
                officialReference: '官方參考 / Official Reference', addressLabel: '地址 / Address', directionsLabel: '交通方式 / Directions',
                byTrain: '搭乘電車 / By train', byCar: '開車 / By car', byPlane: '搭乘飛機 / By plane',
                openOfficial: '開啟官網 / Open Official Page',
                catalogTitle: '東橫飯店資料 / Toyoko Hotel Data', catalogChecking: '正在核對東橫官網飯店清單 / Checking Toyoko hotel list',
                catalogFresh: '東橫飯店資料已是最新 / Toyoko hotel data is current', catalogUpdated: '東橫飯店資料已更新 / Toyoko hotel data updated',
                catalogFailed: '背景更新失敗，繼續使用原快取 / Refresh failed; using the previous cache',
                catalogMeta: '日本營業飯店 {open} 家 · 座標 {coords} 家 · {cache} · {checked}',
                catalogCacheFresh: '快取有效 / Cache fresh', catalogCacheStale: '快取已過期 / Cache expired',
                catalogNeverChecked: '尚未檢查 / Never checked', catalogCheckedAt: '檢查於 {time} / Checked',
                catalogUpcoming: '即將開業 {count} 家 / {count} upcoming: {hotels}',
                catalogNewTitle: '發現 {count} 家新開業飯店 / {count} newly opened hotel(s)',
                catalogRefresh: '重新整理飯店資料 / Refresh', catalogAcknowledge: '知道了 / Dismiss',
                catalogRefreshQueued: '已在背景開始重新整理 / Background refresh started',
                catalogUnresolved: '其中 {count} 家暫缺座標 / {count} hotel(s) still need coordinates',
                hotelBrands: '飯店品牌 / Hotel Brands', toyokoProvider: '東橫 / Toyoko Inn', routeinnProvider: '露櫻 / Route Inn Hotels', dormyProvider: '多美迎 / Dormy Inn', mystaysProvider: 'MYSTAYS Hotel', daiwaProvider: '大和ROYNET / Daiwa Roynet',
                routeinnProviderNote: '露櫻包含露櫻、露櫻Grandia、Grandvrio、ARK / Route Inn includes Route Inn, Grandia, Grandvrio, and ARK.',
                providerRequired: '請至少選擇一個飯店品牌。 / Select at least one hotel brand.',
                quickDates: '快捷日期 / Quick Dates', allBrands: '全部品牌 / All brands', selectedOnly: '僅看已選 / Selected only',
                listView: '列表 / List', mapView: '地圖 / Map', visibleHotels: '顯示 {shown} / {total} 家飯店 / Showing {shown} of {total} hotels',
                sortCode: '編號 / Code', decreasePeople: '減少人數 / Decrease people', increasePeople: '增加人數 / Increase people',
                decreaseRooms: '減少房間 / Decrease rooms', increaseRooms: '增加房間 / Increase rooms',
                toyokoShort: '東橫', routeinnShort: '露櫻', dormyShort: '多美迎', mystaysShort: 'MYSTAYS', daiwaShort: '大和ROYNET', partialProviderFailure: '部分品牌載入失敗 / Some brands failed to load'
              },
              ja: {
                navSearch: '空室検索 / Vacancy Search', navMonitor: '空室監視 / Vacancy Monitor', interfaceSettings: '表示設定 / Interface Settings',
                collapseNav: 'ナビを折りたたむ / Collapse navigation', expandNav: 'ナビを展開 / Expand navigation',
                guideOpen: '使い方ガイド / Guide', guideClose: 'ガイドを閉じる / Close guide', guideTitle: '東横ちゃん使い方ガイド / Toyoko Chan Guide',
                guideSkip: 'あとで / Skip', guideBack: '戻る / Back', guideNext: '次へ / Next', guideFinish: '完了 / Finish', guideProgress: 'ガイド進捗 / Guide progress',
                guideStep1Title: '画面の見方 / Interface Overview', guideStep1Body: '左側のナビで作業画面を切り替えます。上部の操作バーから一回検索、開始、停止をいつでも実行できます。 / Use the sidebar to switch workspaces; the top command bar keeps scan, start, and stop within reach.', guideStep1Tip: 'ヒント：検索開始後は空室監視へ自動で移動します。 / Tip: Starting a scan automatically opens Vacancy Monitor.',
                guideStep2Title: 'ホテルを検索 / Find Hotels', guideStep2Body: '日付、人数、部屋タイプ、会員状態、ブランドを設定し、エリアまたは半径モードでホテルを読み込んで選択します。 / Set dates, guests, room and membership first, then choose brands. Load hotels by area or radius and check the hotels to scan.', guideStep2Tip: 'ヒント：ホテル選択は検索履歴に保存され、次回復元できます。 / Tip: Hotel selections are saved with search history and can be restored next time.',
                guideStep3Title: '空室結果を確認 / Review Results', guideStep3Body: '空室監視では空室あり、空室なし、要確認の状態と価格、残数、部屋タイプを確認できます。 / Vacancy Monitor shows available, unavailable and check states with price, quantity and room type. Hotel and room links open official detail or booking pages.', guideStep3Tip: 'ヒント：絞り込み、検索、変化タブで最新の変化を確認できます。 / Tip: Filters, search and the Changes tab help surface the latest updates.',
                guideStep4Title: '検索設定 / Search Settings', guideStep4Body: '日常利用は軽量な HTTP/API を推奨します。スマート並列と検索間隔で効率とアクセス頻度を調整します。 / HTTP/API is the lightweight daily choice. Smart Parallel helps with larger lists, while Scan Cadence controls rounds, hotel delay and jitter.', guideStep4Tip: '推奨：ラウンド間隔は 120 秒以上、自動バックオフは有効のままにします。 / Recommended: use 120+ second rounds and keep Adaptive Backoff enabled.',
                guideStep5Title: '通知設定 / Push Settings', guideStep5Body: '通知イベントを選び、Bark、ServerChan、Telegram、ローカル通知、メールを必要に応じて設定します。 / Choose notification events, then enable Bark, Server Chan, Telegram, Local Notifications or Email.', guideStep5Tip: 'ヒント：監視前にテスト通知で端末と権限を確認してください。 / Tip: Send a test notification before monitoring to verify the device and system permissions.',
                workspace: '空室追跡ワークスペース / Vacancy workspace', sidebarHotelCount: '{count} 件 / {count} hotels',
                searchViewHelp: '宿泊条件とホテル範囲を設定して検索を開始します。 / Set stay conditions, hotel scope, and start searching.',
                monitorViewHelp: '実行状況、空室結果、通知状態を確認します。 / Review live status, vacancy results, and notifications.',
                searchSettingsViewHelp: '検索エンジン、並列処理、検索間隔を調整します。 / Tune the engine, parallel strategy, and scan cadence.',
                pushSettingsViewHelp: '通知イベントと通知先を設定します。 / Choose alert events and configure notification channels.',
                interfaceViewHelp: '主言語とテーマを選択します。設定はこのブラウザに保存されます。 / Choose language and theme; preferences stay in this browser.',
                theme: 'テーマ / Theme', language: '言語 / Language', languageHelp: '主言語は常に英語と併記されます。 / The primary language is always paired with English.',
                themeHelp: 'システム連動、ライト、ダークから選択できます。 / Follow the system or choose a fixed light or dark theme.',
                themeSystem: 'システム / System', themeLight: 'ライト / Light', themeDark: 'ダーク / Dark',
                areaMode: 'エリアモード / Area', radiusMode: '半径モード / Radius',
                placeAddressCoordinates: '地名・住所または座標 / Place, Address, or Coordinates',
                radius: '半径 / Radius', loadNearby: '周辺ホテルを検索 / Load Nearby',
                radiusHelp: '住所は OpenStreetMap/Nominatim で座標化し、上で選択したホテルブランドを検索します。 / Addresses use OpenStreetMap/Nominatim and the hotel brands selected above.',
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
                updateOpen: 'ソフトウェア更新 / Software Update', updateClose: '更新画面を閉じる / Close update dialog',
                updateDialogTitle: 'ソフトウェア更新 / Software Update', updateDialogKicker: 'バージョンとプロジェクト / VERSION & PROJECT',
                currentVersionLabel: '現在のバージョン / Current Version', latestVersionLabel: '最新バージョン / Latest Version',
                versionInformation: 'バージョン情報 / Version Information',
                authorLabel: '作者 / Author', githubLabel: 'ソースコード / Source Code', checkAgain: '再確認 / Check Again',
                checkingUpdate: '更新を確認中 / Checking for updates', checkingUpdateMessage: '空室検索を妨げず、バックグラウンドで PyPI に接続しています。 / Contacting PyPI in the background without interrupting vacancy scans.',
                upToDate: '最新版です / Up to date', upToDateMessage: 'インストール済みのバージョンは PyPI の最新版です。 / The installed version is the latest version on PyPI.',
                updateAvailableDetail: '新しいバージョンをバックグラウンドで更新できます。 / A new version is available and can be installed in the background.',
                updateFailedTitle: '更新確認に失敗 / Update check failed', updateFailedMessage: '最新バージョン情報を取得できません。後でもう一度お試しください。 / Latest version information is unavailable. Try again later.',
                updateUnknown: '未確認 / Not checked yet',
                currentAction: '状態 / Current', memberPrice: '会員価格 / Member', memberPriceUnknown: '会員価格不明 / Member price unknown',
                nonMemberPrice: '非会員価格 / Non-member', sentOk: '送信成功 / sent OK',
                terminalNotifierSentOk: 'terminal-notifier 送信成功 / terminal-notifier sent OK',
                osascriptSentOk: 'osascript 送信成功 / osascript sent OK',
                scanOnce: '一回検索 / Scan Once', scanningOnce: '一回検索を開始しました / Single scan started.', restart: '再起動 / Restart',
                dockNoHotels: 'ホテル未選択 / No hotels selected', dockSelected: '{count} 件のホテルを選択 / {count} hotels selected',
                selectedSummary: '{selected} / {total} 件選択 / Selected', invalidDates: 'チェックアウト日はチェックイン日より後にしてください。 / Check-out must be after check-in.',
                allFilter: 'すべて / All', sort: '並び替え / Sort', sortDefault: '既定 / Default', sortStatus: '状態 / Status', sortPrice: '料金 / Price', sortName: 'ホテル名 / Hotel', sortDistance: '距離 / Distance',
                showingResults: '{shown} / {total} 件表示 / Showing', noFilteredResults: 'この絞り込みに一致する結果はありません / No results match this filter',
                configReady: '設定同期済み / Configuration ready', configPending: '未適用の変更があります / Changes apply on next start',
                connectionOnline: '接続済み / Connected', connectionOffline: '接続が切れました。再接続中 / Reconnecting',
                snapshotHotels: 'ホテル / Hotels', resultBecameAvailable: '{count} 件のホテルに空室が出ました / {count} hotel(s) became available',
                resultNoLongerAvailable: '{count} 件のホテルが満室になりました / {count} hotel(s) no longer available',
                resultRoomCountChanged: '{count} 件のホテルで室数が変わりました / Room count changed at {count} hotel(s)',
                changesFilter: '変更 / Changes', resultSearchPlaceholder: '番号・ホテル・部屋タイプを検索 / Search code, hotel, or room',
                refreshResults: '更新 / Refresh', exportResults: 'CSV 出力 / Export',
                lastUpdated: '{time} に更新 / Updated', neverUpdated: '未更新 / Never updated',
                exportNoResults: '現在の表示に出力できる結果がありません。 / No visible results to export.',
                adaptiveBackoff: '適応バックオフを有効化 / Adaptive Backoff',
                adaptiveBackoffHelp: 'アクセス異常が 50% 以上になると次回間隔を 2 倍、連続異常では最大 4 倍にします。正常なラウンドで自動復帰します。 / Automatically slows the next round to 2x when checks fail at 50% or more, up to 4x for consecutive unhealthy rounds.',
                safety: '流量保護 / Safety', safetyNormal: '正常 / Normal',
                safetyBackoff: 'バックオフ {multiplier}× · 異常 {ratio}% / Backoff',
                hotelInfo: 'ホテル情報 / Hotel Info', loadingHotelInfo: '公式情報を読み込み中 / Loading official information...',
                hotelInfoUnavailable: '公式情報を一時的に読み込めません / Official information is unavailable.',
                officialReference: '公式情報 / Official Reference', addressLabel: '住所 / Address', directionsLabel: 'アクセス / Directions',
                byTrain: '電車で / By train', byCar: '車で / By car', byPlane: '飛行機で / By plane',
                openOfficial: '公式ページを開く / Open Official Page',
                catalogTitle: '東横ホテルデータ / Toyoko Hotel Data', catalogChecking: '東横の公式ホテル一覧を確認中 / Checking Toyoko hotel list',
                catalogFresh: '東横ホテルデータは最新です / Toyoko hotel data is current', catalogUpdated: '東横ホテルデータを更新しました / Toyoko hotel data updated',
                catalogFailed: '更新に失敗したため以前のキャッシュを使用中 / Refresh failed; using the previous cache',
                catalogMeta: '日本国内営業中 {open} 件 · 座標 {coords} 件 · {cache} · {checked}',
                catalogCacheFresh: 'キャッシュ有効 / Cache fresh', catalogCacheStale: 'キャッシュ期限切れ / Cache expired',
                catalogNeverChecked: '未確認 / Never checked', catalogCheckedAt: '{time} に確認 / Checked',
                catalogUpcoming: '開業予定 {count} 件 / {count} upcoming: {hotels}',
                catalogNewTitle: '新規開業ホテル {count} 件 / {count} newly opened hotel(s)',
                catalogRefresh: 'ホテルデータ更新 / Refresh', catalogAcknowledge: '確認済み / Dismiss',
                catalogRefreshQueued: 'バックグラウンド更新を開始しました / Background refresh started',
                catalogUnresolved: '座標未取得 {count} 件 / {count} hotel(s) still need coordinates',
                hotelBrands: 'ホテルブランド / Hotel Brands', toyokoProvider: '東横 / Toyoko Inn', routeinnProvider: 'ルートイン / Route Inn Hotels', dormyProvider: 'ドーミーイン / Dormy Inn', mystaysProvider: 'ホテルマイステイズ / MYSTAYS Hotel', daiwaProvider: 'ダイワロイネット / Daiwa Roynet',
                routeinnProviderNote: 'ルートインにはルートイン、Grandia、Grandvrio、ARK が含まれます / Route Inn includes Route Inn, Grandia, Grandvrio, and ARK.',
                providerRequired: 'ホテルブランドを1つ以上選択してください。 / Select at least one hotel brand.',
                quickDates: 'クイック日付 / Quick Dates', allBrands: '全ブランド / All brands', selectedOnly: '選択済みのみ / Selected only',
                listView: '一覧 / List', mapView: '地図 / Map', visibleHotels: '{shown} / {total} 件を表示 / Showing {shown} of {total} hotels',
                sortCode: '番号 / Code', decreasePeople: '人数を減らす / Decrease people', increasePeople: '人数を増やす / Increase people',
                decreaseRooms: '部屋数を減らす / Decrease rooms', increaseRooms: '部屋数を増やす / Increase rooms',
                toyokoShort: '東横', routeinnShort: 'ルートイン', dormyShort: 'ドーミーイン', mystaysShort: 'マイステイズ', daiwaShort: 'ダイワ', partialProviderFailure: '一部ブランドの読込に失敗 / Some brands failed to load'
              },
              ko: {
                navSearch: '빈 객실 검색 / Vacancy Search', navMonitor: '빈 객실 모니터 / Vacancy Monitor', interfaceSettings: '화면 설정 / Interface Settings',
                collapseNav: '탐색 메뉴 접기 / Collapse navigation', expandNav: '탐색 메뉴 펼치기 / Expand navigation',
                guideOpen: '사용 안내 / Guide', guideClose: '안내 닫기 / Close guide', guideTitle: '토요코 짱 사용 안내 / Toyoko Chan Guide',
                guideSkip: '나중에 / Skip', guideBack: '이전 / Back', guideNext: '다음 / Next', guideFinish: '완료 / Finish', guideProgress: '안내 진행 / Guide progress',
                guideStep1Title: '화면 둘러보기 / Interface Overview', guideStep1Body: '왼쪽 탐색 메뉴에서 작업 화면을 바꾸고, 상단 작업 막대에서 한 번 검색, 시작, 중지를 실행합니다. / Use the sidebar to switch workspaces; the top command bar keeps scan, start, and stop within reach.', guideStep1Tip: '팁: 검색을 시작하면 빈 객실 모니터로 자동 이동합니다. / Tip: Starting a scan automatically opens Vacancy Monitor.',
                guideStep2Title: '호텔 검색 / Find Hotels', guideStep2Body: '날짜, 인원, 객실 유형, 회원 상태와 브랜드를 설정한 뒤 지역 또는 반경 모드로 호텔을 불러와 선택합니다. / Set dates, guests, room and membership first, then choose brands. Load hotels by area or radius and check the hotels to scan.', guideStep2Tip: '팁: 호텔 선택은 검색 기록에 저장되어 다음에 복원됩니다. / Tip: Hotel selections are saved with search history and can be restored next time.',
                guideStep3Title: '빈 객실 결과 확인 / Review Results', guideStep3Body: '빈 객실 모니터에서 이용 가능, 이용 불가, 확인 필요 상태와 가격, 잔여 수, 객실 유형을 확인합니다. / Vacancy Monitor shows available, unavailable and check states with price, quantity and room type. Hotel and room links open official detail or booking pages.', guideStep3Tip: '팁: 필터, 검색, 변경 탭으로 최신 변화를 빠르게 찾을 수 있습니다. / Tip: Filters, search and the Changes tab help surface the latest updates.',
                guideStep4Title: '검색 설정 / Search Settings', guideStep4Body: '일상 검색에는 가벼운 HTTP/API를 권장합니다. 스마트 병렬과 검색 주기로 효율과 접근 간격을 조정합니다. / HTTP/API is the lightweight daily choice. Smart Parallel helps with larger lists, while Scan Cadence controls rounds, hotel delay and jitter.', guideStep4Tip: '권장: 라운드는 120초 이상, 적응형 백오프는 활성화 상태로 유지하세요. / Recommended: use 120+ second rounds and keep Adaptive Backoff enabled.',
                guideStep5Title: '푸시 설정 / Push Settings', guideStep5Body: '알림 이벤트를 고른 뒤 Bark, ServerChan, Telegram, 로컬 알림 또는 이메일을 설정합니다. / Choose notification events, then enable Bark, Server Chan, Telegram, Local Notifications or Email.', guideStep5Tip: '팁: 모니터링 전에 테스트 알림으로 기기와 권한을 확인하세요. / Tip: Send a test notification before monitoring to verify the device and system permissions.',
                workspace: '빈 객실 추적 작업 공간 / Vacancy workspace', sidebarHotelCount: '{count}개 호텔 / {count} hotels',
                searchViewHelp: '숙박 조건과 호텔 범위를 설정하고 검색을 시작합니다. / Set stay conditions, hotel scope, and start searching.',
                monitorViewHelp: '실행 상태, 객실 결과와 알림 상태를 확인합니다. / Review live status, vacancy results, and notifications.',
                searchSettingsViewHelp: '검색 엔진, 병렬 전략과 검색 주기를 조정합니다. / Tune the engine, parallel strategy, and scan cadence.',
                pushSettingsViewHelp: '알림 이벤트와 알림 채널을 설정합니다. / Choose alert events and configure notification channels.',
                interfaceViewHelp: '주 언어와 테마를 선택합니다. 설정은 이 브라우저에 저장됩니다. / Choose language and theme; preferences stay in this browser.',
                theme: '테마 / Theme', language: '언어 / Language', languageHelp: '주 언어는 항상 영어와 함께 표시됩니다. / The primary language is always paired with English.',
                themeHelp: '시스템, 라이트 또는 다크 테마를 선택할 수 있습니다. / Follow the system or choose a fixed light or dark theme.',
                themeSystem: '시스템 / System', themeLight: '라이트 / Light', themeDark: '다크 / Dark',
                areaMode: '지역 모드 / Area', radiusMode: '반경 모드 / Radius',
                placeAddressCoordinates: '장소, 주소 또는 좌표 / Place, Address, or Coordinates',
                radius: '반경 / Radius', loadNearby: '주변 호텔 찾기 / Load Nearby',
                radiusHelp: '주소는 OpenStreetMap/Nominatim으로 좌표화하고 위에서 선택한 호텔 브랜드를 검색합니다. / Addresses use OpenStreetMap/Nominatim and the hotel brands selected above.',
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
                updateOpen: '소프트웨어 업데이트 / Software Update', updateClose: '업데이트 창 닫기 / Close update dialog',
                updateDialogTitle: '소프트웨어 업데이트 / Software Update', updateDialogKicker: '버전 및 프로젝트 / VERSION & PROJECT',
                currentVersionLabel: '현재 버전 / Current Version', latestVersionLabel: '최신 버전 / Latest Version',
                versionInformation: '버전 정보 / Version Information',
                authorLabel: '작성자 / Author', githubLabel: '소스 코드 / Source Code', checkAgain: '다시 확인 / Check Again',
                checkingUpdate: '업데이트 확인 중 / Checking for updates', checkingUpdateMessage: '빈 객실 검색을 방해하지 않고 백그라운드에서 PyPI에 연결합니다. / Contacting PyPI in the background without interrupting vacancy scans.',
                upToDate: '최신 버전 / Up to date', upToDateMessage: '설치된 버전이 PyPI의 최신 버전입니다. / The installed version is the latest version on PyPI.',
                updateAvailableDetail: '새 버전을 백그라운드에서 바로 설치할 수 있습니다. / A new version is available and can be installed in the background.',
                updateFailedTitle: '업데이트 확인 실패 / Update check failed', updateFailedMessage: '최신 버전 정보를 가져올 수 없습니다. 나중에 다시 확인하세요. / Latest version information is unavailable. Try again later.',
                updateUnknown: '확인 전 / Not checked yet',
                currentAction: '상태 / Current', memberPrice: '회원가 / Member', memberPriceUnknown: '회원가 알 수 없음 / Member price unknown',
                nonMemberPrice: '비회원가 / Non-member', sentOk: '전송 성공 / sent OK',
                terminalNotifierSentOk: 'terminal-notifier 전송 성공 / terminal-notifier sent OK',
                osascriptSentOk: 'osascript 전송 성공 / osascript sent OK',
                scanOnce: '한 번 검색 / Scan Once', scanningOnce: '한 번 검색을 시작했습니다 / Single scan started.', restart: '다시 시작 / Restart',
                dockNoHotels: '선택한 호텔 없음 / No hotels selected', dockSelected: '호텔 {count}개 선택 / {count} hotels selected',
                selectedSummary: '{selected} / {total}개 선택 / Selected', invalidDates: '체크아웃 날짜는 체크인 날짜보다 뒤여야 합니다. / Check-out must be after check-in.',
                allFilter: '전체 / All', sort: '정렬 / Sort', sortDefault: '기본 / Default', sortStatus: '상태 / Status', sortPrice: '가격 / Price', sortName: '호텔명 / Hotel', sortDistance: '거리 / Distance',
                showingResults: '{shown} / {total}개 표시 / Showing', noFilteredResults: '현재 필터와 일치하는 결과가 없습니다 / No results match this filter',
                configReady: '설정 동기화됨 / Configuration ready', configPending: '아직 적용되지 않은 변경 사항 / Changes apply on next start',
                connectionOnline: '연결됨 / Connected', connectionOffline: '연결 끊김, 다시 연결 중 / Reconnecting',
                snapshotHotels: '호텔 / Hotels', resultBecameAvailable: '호텔 {count}곳에 객실이 생겼습니다 / {count} hotel(s) became available',
                resultNoLongerAvailable: '호텔 {count}곳의 객실이 없어졌습니다 / {count} hotel(s) no longer available',
                resultRoomCountChanged: '호텔 {count}곳의 객실 수가 변경되었습니다 / Room count changed at {count} hotel(s)',
                changesFilter: '변경 / Changes', resultSearchPlaceholder: '번호, 호텔 또는 객실 검색 / Search code, hotel, or room',
                refreshResults: '새로고침 / Refresh', exportResults: 'CSV 내보내기 / Export',
                lastUpdated: '{time} 업데이트 / Updated', neverUpdated: '업데이트 전 / Never updated',
                exportNoResults: '현재 보기에 내보낼 결과가 없습니다. / No visible results to export.',
                adaptiveBackoff: '적응형 백오프 사용 / Adaptive Backoff',
                adaptiveBackoffHelp: '접근 오류가 50% 이상이면 다음 주기를 2배로 늦추고, 연속 오류 시 최대 4배까지 적용합니다. 정상 라운드 후 자동 복구됩니다. / Automatically slows the next round to 2x when checks fail at 50% or more, up to 4x for consecutive unhealthy rounds.',
                safety: '트래픽 보호 / Safety', safetyNormal: '정상 / Normal',
                safetyBackoff: '백오프 {multiplier}× · 오류 {ratio}% / Backoff',
                hotelInfo: '호텔 정보 / Hotel Info', loadingHotelInfo: '공식 정보를 불러오는 중 / Loading official information...',
                hotelInfoUnavailable: '공식 정보를 일시적으로 불러올 수 없습니다 / Official information is unavailable.',
                officialReference: '공식 정보 / Official Reference', addressLabel: '주소 / Address', directionsLabel: '교통편 / Directions',
                byTrain: '전철 / By train', byCar: '자동차 / By car', byPlane: '비행기 / By plane',
                openOfficial: '공식 페이지 열기 / Open Official Page',
                catalogTitle: '토요코인 호텔 데이터 / Toyoko Hotel Data', catalogChecking: '토요코인 공식 호텔 목록 확인 중 / Checking Toyoko hotel list',
                catalogFresh: '토요코인 호텔 데이터가 최신입니다 / Toyoko hotel data is current', catalogUpdated: '토요코인 호텔 데이터를 업데이트했습니다 / Toyoko hotel data updated',
                catalogFailed: '업데이트 실패로 이전 캐시 사용 중 / Refresh failed; using the previous cache',
                catalogMeta: '일본 영업 호텔 {open}개 · 좌표 {coords}개 · {cache} · {checked}',
                catalogCacheFresh: '캐시 유효 / Cache fresh', catalogCacheStale: '캐시 만료 / Cache expired',
                catalogNeverChecked: '확인 전 / Never checked', catalogCheckedAt: '{time} 확인 / Checked',
                catalogUpcoming: '개장 예정 {count}개 / {count} upcoming: {hotels}',
                catalogNewTitle: '신규 개장 호텔 {count}개 / {count} newly opened hotel(s)',
                catalogRefresh: '호텔 데이터 새로고침 / Refresh', catalogAcknowledge: '확인 / Dismiss',
                catalogRefreshQueued: '백그라운드 새로고침 시작 / Background refresh started',
                catalogUnresolved: '좌표 미확인 {count}개 / {count} hotel(s) still need coordinates',
                hotelBrands: '호텔 브랜드 / Hotel Brands', toyokoProvider: '토요코인 / Toyoko Inn', routeinnProvider: '루트인 / Route Inn Hotels', dormyProvider: '도미인 / Dormy Inn', mystaysProvider: '마이스테이즈 / MYSTAYS Hotel', daiwaProvider: '다이와 로이넷 / Daiwa Roynet',
                routeinnProviderNote: '루트인에는 Route Inn, Grandia, Grandvrio, ARK가 포함됩니다 / Route Inn includes Route Inn, Grandia, Grandvrio, and ARK.',
                providerRequired: '호텔 브랜드를 하나 이상 선택해 주세요. / Select at least one hotel brand.',
                quickDates: '빠른 날짜 / Quick Dates', allBrands: '모든 브랜드 / All brands', selectedOnly: '선택 항목만 / Selected only',
                listView: '목록 / List', mapView: '지도 / Map', visibleHotels: '{shown} / {total}개 호텔 표시 / Showing {shown} of {total} hotels',
                sortCode: '번호 / Code', decreasePeople: '인원 줄이기 / Decrease people', increasePeople: '인원 늘리기 / Increase people',
                decreaseRooms: '객실 줄이기 / Decrease rooms', increaseRooms: '객실 늘리기 / Increase rooms',
                toyokoShort: '토요코인', routeinnShort: '루트인', dormyShort: '도미인', mystaysShort: '마이스테이즈', daiwaShort: '다이와', partialProviderFailure: '일부 브랜드 불러오기 실패 / Some brands failed to load'
              }
            };
            const MOBILE_UI18N = {
              zh_cn: {
                mobileAccessTitle:'手机访问', mobileAccessHelp:'通过同一 Wi-Fi、Tailscale 或受保护的公网地址连接手机。',
                enableMobileAccess:'启用手机访问', mobileApply:'应用', mobileDisabled:'仅限本机', mobileDisabledHelp:'手机访问未启用。',
                mobileReady:'手机访问已就绪', mobileReadyHelp:'打开下方地址或扫描二维码，并输入配对码。', mobileRestart:'需要重启应用',
                mobileRestartEnable:'设置已保存。重启东横酱后即可从手机访问。', mobileRestartDisable:'设置已保存。重启后将恢复为仅限本机。',
                mobileRemote:'手机已安全连接', mobileRemoteHelp:'局域网会话已通过配对认证；访问设置只能在 Mac 上更改。', mobileLoading:'正在读取状态',
                mobileError:'手机访问状态读取失败', mobileAddress:'手机访问地址', pairingCode:'配对码', copy:'复制', rotate:'更换',
                mobileNote:'Mac 与手机需连接同一可信网络。首次连接时输入配对码，之后会保留登录状态。', mobileQr:'使用手机相机扫码连接',
                mobileCopied:'地址已复制', mobileSaved:'设置已保存', mobileQrMissing:'安装 mobile 可选依赖后可显示二维码。',
                mobileRestarting:'正在重启应用', mobileRestartingHelp:'正在切换网络监听模式，页面恢复后会自动刷新。', mobileRestartFailed:'应用重启超时，请手动重新打开东横酱。',
                mobileChooseConnection:'1. 选择连接方式', mobileLanTitle:'同一 Wi-Fi', mobileLanHelp:'适合在家中或酒店内使用', mobileTailscaleTitle:'Tailscale 远程', mobileTailscaleHelp:'离开当前 Wi-Fi 后也可安全连接', mobilePublicTitle:'公网直连', mobilePublicHelp:'仅建议配合 HTTPS 使用',
                mobileAvailable:'可用', mobileUnavailable:'未检测到', mobileNeedsSetup:'需配置', mobileOpen:'打开地址', mobileAddress:'2. 在手机打开此地址', pairingCode:'3. 输入配对码', mobileStepNetwork:'连接网络', mobileStepScan:'扫码或打开地址', mobileStepPair:'完成配对', mobilePublicPlaceholder:'https://域名或公网IP:端口',
                mobileLanNote:'手机与 Mac 连接同一可信 Wi-Fi。首次输入配对码后会保留登录状态。', mobileTailscaleNote:'两台设备需登录同一 Tailscale 网络；无需公网 IP，也不会把端口暴露到互联网。', mobilePublicNote:'填写完成端口转发或反向代理后的公网地址并点击“应用”。允许 HTTP，但强烈建议先配置 HTTPS。'
              },
              zh_tw: {
                mobileAccessTitle:'手機存取', mobileAccessHelp:'透過同一 Wi-Fi、Tailscale 或受保護的公網位址連接手機。',
                enableMobileAccess:'啟用手機存取', mobileApply:'套用', mobileDisabled:'僅限本機', mobileDisabledHelp:'手機存取尚未啟用。',
                mobileReady:'手機存取已就緒', mobileReadyHelp:'開啟下方網址或掃描 QR Code，並輸入配對碼。', mobileRestart:'需要重新啟動應用程式',
                mobileRestartEnable:'設定已儲存。重新啟動東橫醬後即可從手機存取。', mobileRestartDisable:'設定已儲存。重新啟動後將恢復為僅限本機。',
                mobileRemote:'手機已安全連線', mobileRemoteHelp:'區域網路工作階段已通過配對驗證；存取設定只能在 Mac 上變更。', mobileLoading:'正在讀取狀態',
                mobileError:'無法讀取手機存取狀態', mobileAddress:'手機存取網址', pairingCode:'配對碼', copy:'複製', rotate:'更換',
                mobileNote:'Mac 與手機需連接同一可信任網路。首次連線時輸入配對碼，之後會保留登入狀態。', mobileQr:'使用手機相機掃描連線',
                mobileCopied:'網址已複製', mobileSaved:'設定已儲存', mobileQrMissing:'安裝 mobile 可選依賴後可顯示 QR Code。',
                mobileRestarting:'正在重新啟動應用程式', mobileRestartingHelp:'正在切換網路監聽模式，服務恢復後頁面會自動重新整理。', mobileRestartFailed:'應用程式重新啟動逾時，請手動重新開啟東橫醬。',
                mobileChooseConnection:'1. 選擇連線方式', mobileLanTitle:'同一 Wi-Fi', mobileLanHelp:'適合在家中或飯店內使用', mobileTailscaleTitle:'Tailscale 遠端', mobileTailscaleHelp:'離開目前 Wi-Fi 後仍可安全連線', mobilePublicTitle:'公網直連', mobilePublicHelp:'僅建議搭配 HTTPS 使用',
                mobileAvailable:'可用', mobileUnavailable:'未偵測到', mobileNeedsSetup:'需設定', mobileOpen:'開啟網址', mobileAddress:'2. 在手機開啟此網址', pairingCode:'3. 輸入配對碼', mobileStepNetwork:'連接網路', mobileStepScan:'掃描或開啟網址', mobileStepPair:'完成配對', mobilePublicPlaceholder:'https://網域或公網IP:連接埠',
                mobileLanNote:'手機與 Mac 需連接同一可信任 Wi-Fi。首次輸入配對碼後會保留登入狀態。', mobileTailscaleNote:'兩台裝置需登入同一 Tailscale 網路；不需公網 IP，也不會將連接埠暴露至網際網路。', mobilePublicNote:'填入完成連接埠轉送或反向代理後的公網網址並按「套用」。允許 HTTP，但強烈建議先設定 HTTPS。'
              },
              ja: {
                mobileAccessTitle:'スマートフォン接続', mobileAccessHelp:'同じ Wi-Fi、Tailscale、または保護された公開アドレスから接続します。',
                enableMobileAccess:'スマートフォン接続を有効にする', mobileApply:'適用', mobileDisabled:'このMacのみ', mobileDisabledHelp:'スマートフォン接続は無効です。',
                mobileReady:'スマートフォン接続の準備完了', mobileReadyHelp:'下のURLを開くかQRコードを読み取り、ペアリングコードを入力してください。', mobileRestart:'アプリの再起動が必要です',
                mobileRestartEnable:'設定を保存しました。東横ちゃんを再起動するとスマートフォンから接続できます。', mobileRestartDisable:'設定を保存しました。再起動後はこのMacからのみ接続できます。',
                mobileRemote:'安全に接続済み', mobileRemoteHelp:'LANセッションはペアリング済みです。接続設定はMacでのみ変更できます。', mobileLoading:'状態を確認中',
                mobileError:'スマートフォン接続の状態を取得できません', mobileAddress:'スマートフォン用URL', pairingCode:'ペアリングコード', copy:'コピー', rotate:'変更',
                mobileNote:'Macとスマートフォンを同じ信頼できるネットワークに接続してください。初回のみコード入力が必要です。', mobileQr:'スマートフォンのカメラで読み取る',
                mobileCopied:'URLをコピーしました', mobileSaved:'設定を保存しました', mobileQrMissing:'mobileオプションをインストールするとQRコードを表示できます。',
                mobileRestarting:'アプリを再起動しています', mobileRestartingHelp:'ネットワーク待受モードを切り替えています。復旧後にページを自動更新します。', mobileRestartFailed:'再起動がタイムアウトしました。東横ちゃんを手動で開き直してください。',
                mobileChooseConnection:'1. 接続方法を選択', mobileLanTitle:'同じ Wi-Fi', mobileLanHelp:'自宅やホテル内での利用向け', mobileTailscaleTitle:'Tailscale リモート', mobileTailscaleHelp:'現在の Wi-Fi の外からも安全に接続', mobilePublicTitle:'公開 IP へ直接接続', mobilePublicHelp:'HTTPS との併用を推奨',
                mobileAvailable:'利用可能', mobileUnavailable:'未検出', mobileNeedsSetup:'要設定', mobileOpen:'アドレスを開く', mobileAddress:'2. スマートフォンで開く', pairingCode:'3. ペアリングコードを入力', mobileStepNetwork:'ネットワーク接続', mobileStepScan:'読取またはURLを開く', mobileStepPair:'ペアリング完了', mobilePublicPlaceholder:'https://ドメインまたは公開IP:ポート',
                mobileLanNote:'スマートフォンと Mac を同じ信頼できる Wi-Fi に接続してください。初回のみコード入力が必要です。', mobileTailscaleNote:'両方の端末を同じ Tailscale ネットワークに接続してください。公開 IP やポート公開は不要です。', mobilePublicNote:'ポート転送またはリバースプロキシ設定後の公開 URL を入力して「適用」を押します。HTTP も利用できますが HTTPS を強く推奨します。'
              },
              ko: {
                mobileAccessTitle:'스마트폰 접속', mobileAccessHelp:'같은 Wi-Fi, Tailscale 또는 보호된 공인 주소를 통해 연결합니다.',
                enableMobileAccess:'스마트폰 접속 사용', mobileApply:'적용', mobileDisabled:'이 Mac 전용', mobileDisabledHelp:'스마트폰 접속이 꺼져 있습니다.',
                mobileReady:'스마트폰 접속 준비 완료', mobileReadyHelp:'아래 주소를 열거나 QR 코드를 스캔한 뒤 페어링 코드를 입력하세요.', mobileRestart:'앱을 다시 시작해야 합니다',
                mobileRestartEnable:'설정을 저장했습니다. Toyoko Chan을 다시 시작하면 스마트폰에서 접속할 수 있습니다.', mobileRestartDisable:'설정을 저장했습니다. 다시 시작하면 이 Mac에서만 접속할 수 있습니다.',
                mobileRemote:'안전하게 연결됨', mobileRemoteHelp:'LAN 세션이 페어링 인증되었습니다. 접속 설정은 Mac에서만 변경할 수 있습니다.', mobileLoading:'상태 확인 중',
                mobileError:'스마트폰 접속 상태를 불러오지 못했습니다', mobileAddress:'스마트폰 접속 주소', pairingCode:'페어링 코드', copy:'복사', rotate:'변경',
                mobileNote:'Mac과 스마트폰을 같은 신뢰할 수 있는 네트워크에 연결하세요. 첫 연결에만 페어링 코드가 필요합니다.', mobileQr:'스마트폰 카메라로 스캔',
                mobileCopied:'주소를 복사했습니다', mobileSaved:'설정을 저장했습니다', mobileQrMissing:'mobile 선택 의존성을 설치하면 QR 코드를 표시할 수 있습니다.',
                mobileRestarting:'앱을 다시 시작하는 중', mobileRestartingHelp:'네트워크 수신 모드를 전환하고 있습니다. 서비스가 복구되면 페이지가 자동으로 새로고침됩니다.', mobileRestartFailed:'앱 다시 시작 시간이 초과되었습니다. Toyoko Chan을 수동으로 다시 열어 주세요.',
                mobileChooseConnection:'1. 연결 방식 선택', mobileLanTitle:'같은 Wi-Fi', mobileLanHelp:'집이나 호텔 내부에서 사용', mobileTailscaleTitle:'Tailscale 원격', mobileTailscaleHelp:'현재 Wi-Fi 밖에서도 안전하게 연결', mobilePublicTitle:'공인 IP 직접 연결', mobilePublicHelp:'HTTPS와 함께 사용 권장',
                mobileAvailable:'사용 가능', mobileUnavailable:'감지되지 않음', mobileNeedsSetup:'설정 필요', mobileOpen:'주소 열기', mobileAddress:'2. 휴대폰에서 이 주소 열기', pairingCode:'3. 페어링 코드 입력', mobileStepNetwork:'네트워크 연결', mobileStepScan:'스캔 또는 주소 열기', mobileStepPair:'페어링 완료', mobilePublicPlaceholder:'https://도메인 또는 공인IP:포트',
                mobileLanNote:'휴대폰과 Mac을 같은 신뢰할 수 있는 Wi-Fi에 연결하세요. 첫 연결에만 코드가 필요합니다.', mobileTailscaleNote:'두 기기가 같은 Tailscale 네트워크에 로그인해야 합니다. 공인 IP나 인터넷 포트 공개는 필요하지 않습니다.', mobilePublicNote:'포트 포워딩 또는 리버스 프록시 설정 후의 공인 URL을 입력하고 적용을 누르세요. HTTP도 가능하지만 HTTPS를 권장합니다.'
              },
              en: {
                mobileAccessTitle:'Mobile Access', mobileAccessHelp:'Connect a phone through the same Wi-Fi, Tailscale, or a protected public address.',
                enableMobileAccess:'Enable mobile access', mobileApply:'Apply', mobileDisabled:'This Mac only', mobileDisabledHelp:'Mobile access is disabled.',
                mobileReady:'Mobile access is ready', mobileReadyHelp:'Open the address below or scan the QR code, then enter the pairing code.', mobileRestart:'Restart required',
                mobileRestartEnable:'Saved. Restart Toyoko Chan to allow phone access.', mobileRestartDisable:'Saved. Restart to return to local-only access.',
                mobileRemote:'Phone securely connected', mobileRemoteHelp:'This LAN session is paired. Access settings can only be changed on the Mac.', mobileLoading:'Reading access status',
                mobileError:'Could not read mobile access status', mobileAddress:'Mobile address', pairingCode:'Pairing code', copy:'Copy', rotate:'Rotate',
                mobileNote:'Connect the Mac and phone to the same trusted network. The first connection requires the pairing code; later sessions stay signed in.', mobileQr:'Scan with the phone camera',
                mobileCopied:'Address copied', mobileSaved:'Settings saved', mobileQrMissing:'Install the mobile extra to display a QR code.',
                mobileRestarting:'Restarting the app', mobileRestartingHelp:'Switching the network listener. This page will refresh when the service is ready.', mobileRestartFailed:'The restart timed out. Reopen Toyoko Chan manually.',
                mobileChooseConnection:'1. Choose a connection', mobileLanTitle:'Same Wi-Fi', mobileLanHelp:'Best at home or inside a hotel', mobileTailscaleTitle:'Tailscale Remote', mobileTailscaleHelp:'Connect securely away from this Wi-Fi', mobilePublicTitle:'Direct Public IP', mobilePublicHelp:'Use with HTTPS only',
                mobileAvailable:'Available', mobileUnavailable:'Not detected', mobileNeedsSetup:'Setup needed', mobileOpen:'Open address', mobileAddress:'2. Open this address on your phone', pairingCode:'3. Enter the pairing code', mobileStepNetwork:'Join the network', mobileStepScan:'Scan or open address', mobileStepPair:'Finish pairing', mobilePublicPlaceholder:'https://domain-or-public-ip:port',
                mobileLanNote:'Connect the phone and Mac to the same trusted Wi-Fi. The first connection requires the pairing code.', mobileTailscaleNote:'Sign both devices into the same Tailscale network. No public IP or internet port exposure is required.', mobilePublicNote:'Enter the public URL after configuring port forwarding or a reverse proxy, then select Apply. HTTP works, but HTTPS is strongly recommended.'
              }
            };
            Object.keys(UI18N_EXTRA).forEach(lang => Object.assign(UI18N[lang] || {}, UI18N_EXTRA[lang]));
            Object.keys(MOBILE_UI18N).forEach(lang => Object.assign(UI18N[lang] || {}, MOBILE_UI18N[lang]));
            const SINGLE_UI_OVERRIDES = {
              zh_cn: {
                languageHelp:'界面仅显示当前选择的语言。', stopped:'已停止', running:'运行中',
                updateAvailableMessage:'当前：v{current} · 最新：v{latest}', secondsAgo:'{seconds} 秒前',
                radiusPlaceholder:'东京站或 35.6812,139.7671', providerCatalogDb:'其他品牌数据库',
                catalogUpdating:'更新中', providerCatalogNew:'发现新酒店：{count}',
                historyNoRegion:'未选择区域', historyAllAreas:'全部区域', historyHotelCount:'{count} 家酒店',
                providerHealth:'来源健康', healthIdle:'等待', healthHealthy:'正常', healthDegraded:'异常', healthCooldown:'冷却',
                providerChecks:'{count} 次', providerAverage:'平均 {ms}ms', priorityHotel:'设为重点酒店', removePriority:'取消重点酒店',
                diagnosticsTitle:'运行诊断', diagnosticsSummary:'自适应调度', diagnosticsThroughput:'吞吐量', diagnosticsEta:'预计剩余', diagnosticsQueue:'队列 / 进行中', diagnosticsLatency:'最慢 P95', diagnosticsPriority:'优先酒店', diagnosticsProtection:'保护事件', diagnosticsCache:'缓存命中', diagnosticsSaved:'节省请求', clearCache:'清除检索缓存', cacheFresh:'缓存 {age}s', cacheValidated:'已验证', cacheFallback:'缓存保底', cacheCleared:'已清除 {count} 条检索缓存', trendTitle:'价格与空房趋势', trendWaiting:'等待历史数据', trendSamples:'{count} 条历史记录', trendPrediction:'空房概率 {probability}% · 可信度 {confidence}%', pwaTitle:'手机桌面版', pwaHelp:'安装到主屏幕，保留最近结果并自动重连。', pwaInstall:'安装到桌面', pwaInstalled:'已作为桌面应用运行', pwaReady:'可安装', pwaIos:'iPhone：使用分享菜单中的“添加到主屏幕”', providerMatrixTitle:'品牌能力矩阵', providerMatrixHelp:'不同官网提供的数据能力可能不同。', simulationTitle:'响应模拟与压力测试', simulationHelp:'使用本地模拟官网响应，不访问真实酒店网站。', simulationRun:'运行测试', eventCenterTitle:'统一事件中心', eventNone:'暂无事件', eventDelivery:'推送'
              },
              zh_tw: {
                languageHelp:'介面僅顯示目前選擇的語言。', stopped:'已停止', running:'執行中',
                updateAvailableMessage:'目前：v{current} · 最新：v{latest}', secondsAgo:'{seconds} 秒前',
                radiusPlaceholder:'東京站或 35.6812,139.7671', providerCatalogDb:'其他品牌資料庫',
                catalogUpdating:'更新中', providerCatalogNew:'發現新飯店：{count}',
                historyNoRegion:'未選擇區域', historyAllAreas:'全部區域', historyHotelCount:'{count} 家飯店',
                providerHealth:'來源健康', healthIdle:'等待', healthHealthy:'正常', healthDegraded:'異常', healthCooldown:'冷卻',
                providerChecks:'{count} 次', providerAverage:'平均 {ms}ms', priorityHotel:'設為重點飯店', removePriority:'取消重點飯店',
                diagnosticsTitle:'執行診斷', diagnosticsSummary:'自適應調度', diagnosticsThroughput:'吞吐量', diagnosticsEta:'預計剩餘', diagnosticsQueue:'佇列 / 進行中', diagnosticsLatency:'最慢 P95', diagnosticsPriority:'優先飯店', diagnosticsProtection:'保護事件', diagnosticsCache:'快取命中', diagnosticsSaved:'節省請求', clearCache:'清除檢索快取', cacheFresh:'快取 {age}s', cacheValidated:'已驗證', cacheFallback:'快取備援', cacheCleared:'已清除 {count} 筆檢索快取', trendTitle:'價格與空房趨勢', trendWaiting:'等待歷史資料', trendSamples:'{count} 筆歷史記錄', trendPrediction:'空房機率 {probability}% · 可信度 {confidence}%', pwaTitle:'手機桌面版', pwaHelp:'安裝到主畫面，保留最近結果並自動重新連線。', pwaInstall:'安裝到桌面', pwaInstalled:'已作為桌面應用執行', pwaReady:'可安裝', pwaIos:'iPhone：使用分享選單的「加入主畫面」', providerMatrixTitle:'品牌能力矩陣', providerMatrixHelp:'不同官網提供的資料能力可能不同。', simulationTitle:'回應模擬與壓力測試', simulationHelp:'使用本機模擬官網回應，不存取真實飯店網站。', simulationRun:'執行測試', eventCenterTitle:'統一事件中心', eventNone:'暫無事件', eventDelivery:'推送'
              },
              ja: {
                languageHelp:'画面には選択した言語のみ表示されます。', stopped:'停止中', running:'実行中',
                updateAvailableMessage:'現在：v{current} · 最新：v{latest}', secondsAgo:'{seconds} 秒前',
                radiusPlaceholder:'東京駅または 35.6812,139.7671', providerCatalogDb:'他ブランドデータベース',
                catalogUpdating:'更新中', providerCatalogNew:'新規ホテル：{count}',
                historyNoRegion:'地域未選択', historyAllAreas:'すべての地域', historyHotelCount:'ホテル {count} 件',
                providerHealth:'接続先の状態', healthIdle:'待機', healthHealthy:'正常', healthDegraded:'異常', healthCooldown:'待機中',
                providerChecks:'{count} 回', providerAverage:'平均 {ms}ms', priorityHotel:'重点ホテルに設定', removePriority:'重点を解除',
                diagnosticsTitle:'実行診断', diagnosticsSummary:'適応型スケジューリング', diagnosticsThroughput:'処理速度', diagnosticsEta:'残り時間', diagnosticsQueue:'待機 / 実行中', diagnosticsLatency:'最遅 P95', diagnosticsPriority:'優先ホテル', diagnosticsProtection:'保護イベント', diagnosticsCache:'キャッシュ命中', diagnosticsSaved:'削減リクエスト', clearCache:'検索キャッシュを消去', cacheFresh:'キャッシュ {age}秒', cacheValidated:'再検証済み', cacheFallback:'キャッシュ代替', cacheCleared:'検索キャッシュを {count} 件消去しました', trendTitle:'料金・空室トレンド', trendWaiting:'履歴データを待っています', trendSamples:'履歴 {count} 件', trendPrediction:'空室確率 {probability}% · 信頼度 {confidence}%', pwaTitle:'モバイルアプリ', pwaHelp:'ホーム画面に追加し、直近の結果を保持して自動再接続します。', pwaInstall:'ホーム画面に追加', pwaInstalled:'アプリとして実行中', pwaReady:'インストール可能', pwaIos:'iPhone：共有メニューから「ホーム画面に追加」', providerMatrixTitle:'ブランド機能マトリクス', providerMatrixHelp:'公式サイトごとに利用できるデータが異なります。', simulationTitle:'レスポンス模擬・負荷テスト', simulationHelp:'実サイトへアクセスせずローカル応答でテストします。', simulationRun:'テスト実行', eventCenterTitle:'統合イベントセンター', eventNone:'イベントはありません', eventDelivery:'通知'
              },
              ko: {
                languageHelp:'화면에는 선택한 언어만 표시됩니다.', stopped:'중지됨', running:'실행 중',
                updateAvailableMessage:'현재: v{current} · 최신: v{latest}', secondsAgo:'{seconds}초 전',
                radiusPlaceholder:'도쿄역 또는 35.6812,139.7671', providerCatalogDb:'기타 브랜드 데이터베이스',
                catalogUpdating:'업데이트 중', providerCatalogNew:'신규 호텔: {count}',
                historyNoRegion:'지역 미선택', historyAllAreas:'전체 지역', historyHotelCount:'호텔 {count}개',
                providerHealth:'연결 상태', healthIdle:'대기', healthHealthy:'정상', healthDegraded:'오류', healthCooldown:'대기 중',
                providerChecks:'{count}회', providerAverage:'평균 {ms}ms', priorityHotel:'중점 호텔로 설정', removePriority:'중점 해제',
                diagnosticsTitle:'실행 진단', diagnosticsSummary:'적응형 스케줄링', diagnosticsThroughput:'처리량', diagnosticsEta:'예상 남은 시간', diagnosticsQueue:'대기 / 실행 중', diagnosticsLatency:'최저속 P95', diagnosticsPriority:'우선 호텔', diagnosticsProtection:'보호 이벤트', diagnosticsCache:'캐시 적중', diagnosticsSaved:'절감 요청', clearCache:'검색 캐시 지우기', cacheFresh:'캐시 {age}초', cacheValidated:'재검증됨', cacheFallback:'캐시 대체', cacheCleared:'검색 캐시 {count}개를 지웠습니다', trendTitle:'가격 및 객실 추세', trendWaiting:'기록 데이터를 기다리는 중', trendSamples:'기록 {count}개', trendPrediction:'객실 확률 {probability}% · 신뢰도 {confidence}%', pwaTitle:'모바일 홈 앱', pwaHelp:'홈 화면에 설치하고 최근 결과와 자동 재연결을 사용합니다.', pwaInstall:'홈 화면에 설치', pwaInstalled:'앱으로 실행 중', pwaReady:'설치 가능', pwaIos:'iPhone: 공유 메뉴에서 “홈 화면에 추가”', providerMatrixTitle:'브랜드 기능 매트릭스', providerMatrixHelp:'공식 사이트마다 제공 데이터가 다를 수 있습니다.', simulationTitle:'응답 시뮬레이션 및 부하 테스트', simulationHelp:'실제 호텔 사이트에 접속하지 않고 로컬 응답으로 테스트합니다.', simulationRun:'테스트 실행', eventCenterTitle:'통합 이벤트 센터', eventNone:'이벤트 없음', eventDelivery:'알림'
              }
            };
            const EN_UI = {
              searchTitle:'Vacancy Search', searchSubtitle:'Choose dates, stay preferences, and hotel scope. Starting a scan saves it to search history.',
              radiusPlaceholder:'Tokyo Station or 35.6812,139.7671', providerCatalogDb:'Other brand database',
              catalogUpdating:'Updating', providerCatalogNew:'New hotels: {count}',
              historyNoRegion:'No region', historyAllAreas:'All areas', historyHotelCount:'{count} hotels',
              providerHealth:'Provider health', healthIdle:'Idle', healthHealthy:'Healthy', healthDegraded:'Degraded', healthCooldown:'Cooldown',
              providerChecks:'{count} checks', providerAverage:'Avg {ms}ms',
              priorityHotel:'Mark as priority hotel', removePriority:'Remove priority', diagnosticsTitle:'Run Diagnostics', diagnosticsSummary:'Adaptive scheduling', diagnosticsThroughput:'Throughput', diagnosticsEta:'Estimated remaining', diagnosticsQueue:'Queued / active', diagnosticsLatency:'Slowest P95', diagnosticsPriority:'Priority hotels', diagnosticsProtection:'Protection events', diagnosticsCache:'Cache hit', diagnosticsSaved:'Requests saved', clearCache:'Clear scan cache', cacheFresh:'Cached {age}s', cacheValidated:'Revalidated', cacheFallback:'Cached backup', cacheCleared:'Cleared {count} cached scan entries', trendTitle:'Price & Availability Trends', trendWaiting:'Waiting for history', trendSamples:'{count} historical observations', trendPrediction:'Availability {probability}% · confidence {confidence}%', pwaTitle:'Mobile Home App', pwaHelp:'Install to the home screen, retain recent results, and reconnect automatically.', pwaInstall:'Install app', pwaInstalled:'Running as an installed app', pwaReady:'Ready to install', pwaIos:'iPhone: use Add to Home Screen in the Share menu', providerMatrixTitle:'Provider Capability Matrix', providerMatrixHelp:'Data capabilities vary by official website.', simulationTitle:'Response Simulation & Stress Test', simulationHelp:'Uses local simulated responses without contacting hotel websites.', simulationRun:'Run test', eventCenterTitle:'Unified Event Center', eventNone:'No events yet', eventDelivery:'Delivery',
              areaHint:'Choose a region. Detail area is optional; leaving it blank loads the full region. Check hotels, then start searching.',
              areaSelected:'Region selected. Load the full region or choose a detail area, then check hotels and start searching.',
              historyHint:'Shows the 10 most recent searches. Identical settings are not duplicated.',
              searchSettingsNote:'Engine, scan cadence, and smart parallel settings are managed here. Smart Parallel applies to HTTP/API only and staggers requests.',
              pushSettingsNote:'Availability, repeat, loss, and start notifications are sent through every enabled channel.',
              engineHelp:'HTTP/API uses fewer requests and is faster. It can fall back to Playwright when parsing fails.',
              smartParallelHelp:'HTTP/API only. Runs brands in parallel, adapts each rate, and prioritizes starred or recently changed hotels.',
              localHelp:'Local notifications use terminal-notifier/osascript on macOS, PowerShell on Windows, and notify-send on Linux.',
              runSubtitle:'Repeatedly scans the current hotel scope. You can stop or adjust settings while running.',
              stopped:'STOPPED', running:'RUNNING', pushSubtitle:'Shows enabled notification channels and their most recent delivery state.',
              tipEngine:'HTTP/API is recommended by default because it is lightweight, fast, and resource efficient. If parsing fails, the app can fall back to Playwright, which behaves more like a real browser but uses more resources.',
              tipSmartParallel:'HTTP/API only. Different brands can run in parallel while each brand keeps its own request interval. A brand with repeated access errors cools down without blocking the others.',
              tipCadence:'Round Interval controls the wait between scans. Per-hotel Base Delay controls access frequency inside a worker. Request Jitter makes timing less uniform. Prefer 120+ second rounds, 2-5 second hotel delays, and 30-50% jitter.',
              tipReminder:'Controls repeat alerts after availability appears. Repeat Count is the number of additional alerts after the first; INF continues indefinitely. Use a cooldown of at least 300 seconds.',
              tipBark:'For iPhone and iPad. 1. Install Bark. 2. Copy the Device Key from the app home screen. 3. Enter it as Bark Key. 4. Keep the default server or enter a self-hosted server. 5. Enable Bark and start searching.',
              tipServerChan:'For WeChat notifications. 1. Sign in to Server Chan. 2. Connect a WeChat channel. 3. Copy the SendKey. 4. Paste it here. 5. Enable the channel and start searching.',
              tipTelegram:'1. Find BotFather in Telegram. 2. Create a bot with /newbot and copy the token. 3. Message the bot or add it to a group. 4. Enter the Chat ID. 5. Enable Telegram and start searching.',
              tipLocal:'Shows notifications on this computer. 1. Enable Local Notifications. 2. Send a test. 3. On macOS check notification permissions; Windows needs PowerShell; Linux needs notify-send and a graphical desktop session.',
              tipEmail:'Sends mail through SMTP. 1. Enable SMTP with your provider. 2. Create an app password. 3. Enter host, port, username, and password. 4. Enter From and To. Port 465 commonly uses SSL/TLS; 587 commonly uses TLS.',
              catalogMeta:'{open} open hotels in Japan · {coords} coordinates · {cache} · {checked}',
              mystaysProvider:'MYSTAYS Hotel', toyokoShort:'Toyoko Inn', routeinnShort:'Route Inn', dormyShort:'Dormy Inn', mystaysShort:'MYSTAYS', daiwaShort:'Daiwa Roynet',
              updateAvailableMessage:'Current: v{current} · Latest: v{latest}', selectedSummary:'Selected {selected} / {total}', showingResults:'Showing {shown} / {total}',
              languageHelp:'The interface shows only the selected language.', secondsAgo:'{seconds}s ago'
            };
            Object.assign(SINGLE_UI_OVERRIDES.zh_cn, {
              navHome:'首页', homeEyebrow:'今日监控台', homeGreeting:'欢迎回来', homeLoading:'正在读取上次的检索与监控状态…',
              homeSetupSearch:'建立检索', homeContinueSearch:'继续上次检索', homeViewMonitor:'查看监控', homeLiveLabel:'监控状态', homeNextScan:'下次检索',
              homeMetricStatus:'监控状态', homeMetricAvailable:'当前空房', homeMetricHotels:'监控酒店', homeMetricNext:'下次检索', homeMetricTraffic:'WebUI 流量', homeTrafficAccesses:'{count} 次访问', homeTrafficTooltip:'WebUI 应用层估算：下行 {down}（{downRate}/s） · 上行 {up}（{upRate}/s） · 页面打开 {visits} 次；不含酒店官网检索流量',
              homeReady:'准备开始', homeSelectedHotels:'{count} 家酒店', homeNoHotels:'尚未选择', homeWaitingStart:'等待启动', homeScanning:'正在检索', homeWaitingRound:'等待下一轮',
              homeTaskKicker:'当前任务', homeTaskEmpty:'尚未建立监控任务', homeTaskReady:'任务已就绪', homeTaskRunning:'正在监控', homeTaskStopped:'待启动',
              homeCheckin:'入住', homeCheckout:'退房', homeNoRegion:'尚未选择区域', homeEditSearch:'修改条件', homeViewResults:'查看实时结果',
              homeActivityKicker:'实时动态', homeActivityTitle:'最新空房变化', homeAllEvents:'全部事件', homeActivityEmpty:'还没有空房变化',
              homeTrendKicker:'数据洞察', homeTrendTitle:'空房与价格趋势', homeViewTrend:'查看趋势', homeTrendRecords:'条历史记录', homeTrendEmpty:'数据会在检索后自动积累',
              homeQuickKicker:'快捷入口', homeQuickTitle:'开始新的操作', homeQuickArea:'区域检索', homeQuickRadius:'方圆检索', homeQuickHistory:'搜索记录', homeQuickPush:'推送设定',
              homeHealthKicker:'系统状态', homeHealthTitle:'服务运行状态', homeChecking:'检查中', homeHealthy:'全部正常', homeAttention:'需要留意',
              homeConnection:'WebUI 连接', homeProviders:'酒店来源', homeNotifications:'推送渠道', homeHistoryData:'历史数据', homeNormal:'正常', homeWaiting:'等待',
              homeEnabledChannels:'{count} 个启用', homeHistoryRecords:'{count} 条', homeProviderReady:'{healthy}/{total} 正常', homeNoProviderChecks:'等待首次检索',
              homeRunningSummary:'正在监控 {count} 家酒店，东横酱会持续留意新的空房变化。', homeStoppedSummary:'已载入 {count} 家酒店，确认条件后即可开始监控。', homeEmptySummary:'先选择日期和酒店，东横酱会持续留意空房变化。',
              homeGuestRoom:'{people} 人 · {rooms} 房', homeProviderCount:'{count} 个品牌',
              eventAvailable:'发现空房', eventUnavailable:'房源已消失', eventCountChanged:'可用数量变化', eventReminder:'空房重复提醒', eventSearchError:'检索需要确认', eventStarted:'搜索已启动', eventStopped:'搜索已停止', eventGeneric:'监控事件',
              homeJustNow:'刚刚', homeMinutesAgo:'{count} 分钟前', homeHoursAgo:'{count} 小时前', homeAvailabilityPrediction:'空房概率 {probability}% · 可信度 {confidence}%', homeNoPrediction:'正在积累样本'
            });
            Object.assign(SINGLE_UI_OVERRIDES.zh_tw, {
              navHome:'首頁', homeEyebrow:'今日監控台', homeGreeting:'歡迎回來', homeLoading:'正在讀取上次的搜尋與監控狀態…',
              homeSetupSearch:'建立搜尋', homeContinueSearch:'繼續上次搜尋', homeViewMonitor:'查看監控', homeLiveLabel:'監控狀態', homeNextScan:'下次搜尋',
              homeMetricStatus:'監控狀態', homeMetricAvailable:'目前空房', homeMetricHotels:'監控飯店', homeMetricNext:'下次搜尋', homeMetricTraffic:'WebUI 流量', homeTrafficAccesses:'{count} 次存取', homeTrafficTooltip:'WebUI 應用層估算：下載 {down}（{downRate}/s） · 上傳 {up}（{upRate}/s） · 頁面開啟 {visits} 次；不含飯店官網搜尋流量', homeReady:'準備開始', homeSelectedHotels:'{count} 家飯店', homeNoHotels:'尚未選擇', homeWaitingStart:'等待啟動', homeScanning:'正在搜尋', homeWaitingRound:'等待下一輪',
              homeTaskKicker:'目前任務', homeTaskEmpty:'尚未建立監控任務', homeTaskReady:'任務已就緒', homeTaskRunning:'正在監控', homeTaskStopped:'待啟動', homeCheckin:'入住', homeCheckout:'退房', homeNoRegion:'尚未選擇區域', homeEditSearch:'修改條件', homeViewResults:'查看即時結果',
              homeActivityKicker:'即時動態', homeActivityTitle:'最新空房變化', homeAllEvents:'全部事件', homeActivityEmpty:'尚無空房變化', homeTrendKicker:'資料洞察', homeTrendTitle:'空房與價格趨勢', homeViewTrend:'查看趨勢', homeTrendRecords:'筆歷史記錄', homeTrendEmpty:'資料會在搜尋後自動累積',
              homeQuickKicker:'快速入口', homeQuickTitle:'開始新的操作', homeQuickArea:'區域搜尋', homeQuickRadius:'方圓搜尋', homeQuickHistory:'搜尋記錄', homeQuickPush:'推送設定', homeHealthKicker:'系統狀態', homeHealthTitle:'服務執行狀態', homeChecking:'檢查中', homeHealthy:'全部正常', homeAttention:'需要留意', homeConnection:'WebUI 連線', homeProviders:'飯店來源', homeNotifications:'推送管道', homeHistoryData:'歷史資料', homeNormal:'正常', homeWaiting:'等待', homeEnabledChannels:'{count} 個啟用', homeHistoryRecords:'{count} 筆', homeProviderReady:'{healthy}/{total} 正常', homeNoProviderChecks:'等待首次搜尋',
              homeRunningSummary:'正在監控 {count} 家飯店，東橫醬會持續留意新的空房變化。', homeStoppedSummary:'已載入 {count} 家飯店，確認條件後即可開始監控。', homeEmptySummary:'先選擇日期和飯店，東橫醬會持續留意空房變化。', homeGuestRoom:'{people} 人 · {rooms} 房', homeProviderCount:'{count} 個品牌',
              eventAvailable:'發現空房', eventUnavailable:'房源已消失', eventCountChanged:'可用數量變化', eventReminder:'空房重複提醒', eventSearchError:'搜尋需要確認', eventStarted:'搜尋已啟動', eventStopped:'搜尋已停止', eventGeneric:'監控事件', homeJustNow:'剛剛', homeMinutesAgo:'{count} 分鐘前', homeHoursAgo:'{count} 小時前', homeAvailabilityPrediction:'空房機率 {probability}% · 可信度 {confidence}%', homeNoPrediction:'正在累積樣本'
            });
            Object.assign(SINGLE_UI_OVERRIDES.ja, {
              navHome:'ホーム', homeEyebrow:'今日のモニター', homeGreeting:'おかえりなさい', homeLoading:'前回の検索と監視状態を読み込んでいます…', homeSetupSearch:'検索を作成', homeContinueSearch:'前回の検索を続ける', homeViewMonitor:'監視を見る', homeLiveLabel:'監視状態', homeNextScan:'次回検索', homeMetricStatus:'監視状態', homeMetricAvailable:'現在の空室', homeMetricHotels:'監視ホテル', homeMetricNext:'次回検索', homeMetricTraffic:'WebUI 通信量', homeTrafficAccesses:'{count} リクエスト', homeTrafficTooltip:'WebUI アプリ層の推定値：受信 {down}（{downRate}/s） · 送信 {up}（{upRate}/s） · ページ表示 {visits} 回。ホテルサイト検索通信は含みません', homeReady:'開始できます', homeSelectedHotels:'ホテル {count} 件', homeNoHotels:'未選択', homeWaitingStart:'開始待ち', homeScanning:'検索中', homeWaitingRound:'次回待ち',
              homeTaskKicker:'現在のタスク', homeTaskEmpty:'監視タスクはありません', homeTaskReady:'準備完了', homeTaskRunning:'監視中', homeTaskStopped:'開始待ち', homeCheckin:'チェックイン', homeCheckout:'チェックアウト', homeNoRegion:'地域未選択', homeEditSearch:'条件を変更', homeViewResults:'リアルタイム結果', homeActivityKicker:'ライブ更新', homeActivityTitle:'最新の空室変化', homeAllEvents:'すべてのイベント', homeActivityEmpty:'空室変化はまだありません', homeTrendKicker:'データ分析', homeTrendTitle:'空室・料金トレンド', homeViewTrend:'トレンドを見る', homeTrendRecords:'件の履歴', homeTrendEmpty:'検索後にデータが蓄積されます',
              homeQuickKicker:'クイック操作', homeQuickTitle:'新しい操作を開始', homeQuickArea:'地域検索', homeQuickRadius:'周辺検索', homeQuickHistory:'検索履歴', homeQuickPush:'通知設定', homeHealthKicker:'システム状態', homeHealthTitle:'サービス稼働状況', homeChecking:'確認中', homeHealthy:'すべて正常', homeAttention:'確認が必要', homeConnection:'WebUI 接続', homeProviders:'ホテル接続先', homeNotifications:'通知先', homeHistoryData:'履歴データ', homeNormal:'正常', homeWaiting:'待機', homeEnabledChannels:'{count} 件有効', homeHistoryRecords:'{count} 件', homeProviderReady:'{healthy}/{total} 正常', homeNoProviderChecks:'初回検索待ち',
              homeRunningSummary:'ホテル {count} 件を監視中です。新しい空室を継続して確認します。', homeStoppedSummary:'ホテル {count} 件を読み込み済みです。条件を確認して監視を開始できます。', homeEmptySummary:'日付とホテルを選ぶと、空室の変化を継続して確認します。', homeGuestRoom:'{people} 名 · {rooms} 室', homeProviderCount:'{count} ブランド', eventAvailable:'空室を発見', eventUnavailable:'空室が終了', eventCountChanged:'空室数が変化', eventReminder:'空室リマインダー', eventSearchError:'検索の確認が必要', eventStarted:'検索を開始', eventStopped:'検索を停止', eventGeneric:'監視イベント', homeJustNow:'たった今', homeMinutesAgo:'{count} 分前', homeHoursAgo:'{count} 時間前', homeAvailabilityPrediction:'空室確率 {probability}% · 信頼度 {confidence}%', homeNoPrediction:'サンプル収集中'
            });
            Object.assign(SINGLE_UI_OVERRIDES.ko, {
              navHome:'홈', homeEyebrow:'오늘의 모니터', homeGreeting:'다시 오신 것을 환영합니다', homeLoading:'이전 검색과 모니터링 상태를 불러오는 중…', homeSetupSearch:'검색 만들기', homeContinueSearch:'이전 검색 계속', homeViewMonitor:'모니터 보기', homeLiveLabel:'모니터 상태', homeNextScan:'다음 검색', homeMetricStatus:'모니터 상태', homeMetricAvailable:'현재 빈 객실', homeMetricHotels:'모니터 호텔', homeMetricNext:'다음 검색', homeMetricTraffic:'WebUI 트래픽', homeTrafficAccesses:'요청 {count}회', homeTrafficTooltip:'WebUI 애플리케이션 계층 추정값: 다운로드 {down}（{downRate}/s） · 업로드 {up}（{upRate}/s） · 페이지 열기 {visits}회. 호텔 사이트 검색 트래픽은 제외됩니다', homeReady:'시작 준비', homeSelectedHotels:'호텔 {count}개', homeNoHotels:'선택 안 됨', homeWaitingStart:'시작 대기', homeScanning:'검색 중', homeWaitingRound:'다음 검색 대기',
              homeTaskKicker:'현재 작업', homeTaskEmpty:'모니터링 작업이 없습니다', homeTaskReady:'작업 준비 완료', homeTaskRunning:'모니터링 중', homeTaskStopped:'시작 대기', homeCheckin:'체크인', homeCheckout:'체크아웃', homeNoRegion:'지역 미선택', homeEditSearch:'조건 수정', homeViewResults:'실시간 결과', homeActivityKicker:'실시간 활동', homeActivityTitle:'최신 빈 객실 변화', homeAllEvents:'모든 이벤트', homeActivityEmpty:'아직 빈 객실 변화가 없습니다', homeTrendKicker:'데이터 인사이트', homeTrendTitle:'객실 및 가격 추세', homeViewTrend:'추세 보기', homeTrendRecords:'개 기록', homeTrendEmpty:'검색 후 데이터가 자동으로 쌓입니다',
              homeQuickKicker:'빠른 실행', homeQuickTitle:'새 작업 시작', homeQuickArea:'지역 검색', homeQuickRadius:'반경 검색', homeQuickHistory:'검색 기록', homeQuickPush:'푸시 설정', homeHealthKicker:'시스템 상태', homeHealthTitle:'서비스 실행 상태', homeChecking:'확인 중', homeHealthy:'모두 정상', homeAttention:'확인 필요', homeConnection:'WebUI 연결', homeProviders:'호텔 공급자', homeNotifications:'알림 채널', homeHistoryData:'기록 데이터', homeNormal:'정상', homeWaiting:'대기', homeEnabledChannels:'{count}개 활성화', homeHistoryRecords:'{count}개', homeProviderReady:'{healthy}/{total} 정상', homeNoProviderChecks:'첫 검색 대기',
              homeRunningSummary:'호텔 {count}개를 모니터링하며 새로운 빈 객실 변화를 확인합니다.', homeStoppedSummary:'호텔 {count}개를 불러왔습니다. 조건을 확인한 후 모니터링을 시작하세요.', homeEmptySummary:'날짜와 호텔을 선택하면 빈 객실 변화를 계속 확인합니다.', homeGuestRoom:'{people}명 · {rooms}실', homeProviderCount:'브랜드 {count}개', eventAvailable:'빈 객실 발견', eventUnavailable:'객실 이용 종료', eventCountChanged:'객실 수 변경', eventReminder:'빈 객실 반복 알림', eventSearchError:'검색 확인 필요', eventStarted:'검색 시작', eventStopped:'검색 중지', eventGeneric:'모니터 이벤트', homeJustNow:'방금', homeMinutesAgo:'{count}분 전', homeHoursAgo:'{count}시간 전', homeAvailabilityPrediction:'객실 확률 {probability}% · 신뢰도 {confidence}%', homeNoPrediction:'샘플 수집 중'
            });
            Object.assign(EN_UI, {
              navHome:'Home', homeEyebrow:'Today’s Monitor', homeGreeting:'Welcome back', homeLoading:'Loading your previous search and monitoring state…', homeSetupSearch:'Create search', homeContinueSearch:'Continue last search', homeViewMonitor:'View monitor', homeLiveLabel:'Monitor status', homeNextScan:'Next scan', homeMetricStatus:'Monitor status', homeMetricAvailable:'Available now', homeMetricHotels:'Monitored hotels', homeMetricNext:'Next scan', homeMetricTraffic:'WebUI traffic', homeTrafficAccesses:'{count} requests', homeTrafficTooltip:'WebUI application-layer estimate: down {down} ({downRate}/s) · up {up} ({upRate}/s) · page views {visits}. Hotel-provider scan traffic is excluded', homeReady:'Ready to start', homeSelectedHotels:'{count} hotels', homeNoHotels:'None selected', homeWaitingStart:'Waiting to start', homeScanning:'Scanning', homeWaitingRound:'Waiting for next round',
              homeTaskKicker:'Current Task', homeTaskEmpty:'No monitoring task yet', homeTaskReady:'Task ready', homeTaskRunning:'Monitoring', homeTaskStopped:'Ready to start', homeCheckin:'Check-in', homeCheckout:'Check-out', homeNoRegion:'No region selected', homeEditSearch:'Edit conditions', homeViewResults:'View live results', homeActivityKicker:'Live Activity', homeActivityTitle:'Latest vacancy changes', homeAllEvents:'All events', homeActivityEmpty:'No vacancy changes yet', homeTrendKicker:'Data Insights', homeTrendTitle:'Availability & price trends', homeViewTrend:'View trends', homeTrendRecords:'historical records', homeTrendEmpty:'History builds automatically after scans',
              homeQuickKicker:'Quick Actions', homeQuickTitle:'Start something new', homeQuickArea:'Area search', homeQuickRadius:'Radius search', homeQuickHistory:'Search history', homeQuickPush:'Push settings', homeHealthKicker:'System Status', homeHealthTitle:'Service health', homeChecking:'Checking', homeHealthy:'All systems normal', homeAttention:'Needs attention', homeConnection:'WebUI connection', homeProviders:'Hotel providers', homeNotifications:'Notification channels', homeHistoryData:'Historical data', homeNormal:'Normal', homeWaiting:'Waiting', homeEnabledChannels:'{count} enabled', homeHistoryRecords:'{count} records', homeProviderReady:'{healthy}/{total} healthy', homeNoProviderChecks:'Waiting for first scan',
              homeRunningSummary:'Monitoring {count} hotels and watching for new vacancy changes.', homeStoppedSummary:'Loaded {count} hotels. Review the conditions and start monitoring when ready.', homeEmptySummary:'Choose dates and hotels, then Toyoko Chan will watch for vacancy changes.', homeGuestRoom:'{people} guests · {rooms} rooms', homeProviderCount:'{count} brands', eventAvailable:'Room available', eventUnavailable:'No longer available', eventCountChanged:'Room count changed', eventReminder:'Availability reminder', eventSearchError:'Search needs review', eventStarted:'Search started', eventStopped:'Search stopped', eventGeneric:'Monitoring event', homeJustNow:'Just now', homeMinutesAgo:'{count}m ago', homeHoursAgo:'{count}h ago', homeAvailabilityPrediction:'Availability {probability}% · confidence {confidence}%', homeNoPrediction:'Collecting samples'
            });
            const TREND_READABLE_UI = {
              zh_cn: {
                trendScopeCurrent:'仅显示当前入住日期、人数、房型等条件下的记录', trendHotel:'酒店', trendRange:'时间范围', trendDays:'{count} 天',
                trendSelectedSummary:'{count} 次检索记录 · {hotels} 家酒店', trendCurrentStatus:'当前状态', trendLatestPrice:'当前最低价', trendHistoricalRate:'近期检索有房率', trendDataAmount:'数据量',
                trendAvailableChecks:'{available}/{known} 次检索有房', trendPriceRange:'历史价格 {min} – {max}', trendUpdated:'更新于 {time}', trendRecordsDetail:'{count} 次检索 · {days} 天范围',
                trendStatusAvailable:'有房', trendStatusUnavailable:'无房', trendStatusUnknown:'需确认', trendNoPrice:'暂无报价', trendNoRoomType:'未取得房型',
                trendPriceAxis:'最低价', trendAvailabilityAxis:'每次检索结果', trendLegendPrice:'最低价', trendLegendAvailable:'有房', trendLegendUnavailable:'无房', trendLegendUnknown:'需确认', trendEachBlock:'每个色块代表一次检索',
                trendRecentChecks:'最近检索明细', trendTime:'检索时间', trendStatus:'状态', trendPrice:'最低价', trendRooms:'剩余', trendRoomType:'房型', trendRoomCount:'{count} 间', trendNoHotelHistory:'当前条件下还没有这家酒店的历史记录',
                homeAvailabilityRate:'近期有房率 {rate}% · {samples} 次检索'
              },
              zh_tw: {
                trendScopeCurrent:'僅顯示目前入住日期、人數、房型等條件下的記錄', trendHotel:'飯店', trendRange:'時間範圍', trendDays:'{count} 天',
                trendSelectedSummary:'{count} 次搜尋記錄 · {hotels} 家飯店', trendCurrentStatus:'目前狀態', trendLatestPrice:'目前最低價', trendHistoricalRate:'近期搜尋有房率', trendDataAmount:'資料量',
                trendAvailableChecks:'{available}/{known} 次搜尋有房', trendPriceRange:'歷史價格 {min} – {max}', trendUpdated:'更新於 {time}', trendRecordsDetail:'{count} 次搜尋 · {days} 天範圍',
                trendStatusAvailable:'有房', trendStatusUnavailable:'無房', trendStatusUnknown:'待確認', trendNoPrice:'暫無報價', trendNoRoomType:'未取得房型',
                trendPriceAxis:'最低價', trendAvailabilityAxis:'每次搜尋結果', trendLegendPrice:'最低價', trendLegendAvailable:'有房', trendLegendUnavailable:'無房', trendLegendUnknown:'待確認', trendEachBlock:'每個色塊代表一次搜尋',
                trendRecentChecks:'最近搜尋明細', trendTime:'搜尋時間', trendStatus:'狀態', trendPrice:'最低價', trendRooms:'剩餘', trendRoomType:'房型', trendRoomCount:'{count} 間', trendNoHotelHistory:'目前條件下尚無這家飯店的歷史記錄',
                homeAvailabilityRate:'近期有房率 {rate}% · {samples} 次搜尋'
              },
              ja: {
                trendScopeCurrent:'現在の宿泊日・人数・部屋条件に一致する履歴のみ表示', trendHotel:'ホテル', trendRange:'期間', trendDays:'{count} 日',
                trendSelectedSummary:'検索履歴 {count} 件 · ホテル {hotels} 件', trendCurrentStatus:'現在の状態', trendLatestPrice:'現在の最低料金', trendHistoricalRate:'直近検索の空室率', trendDataAmount:'データ量',
                trendAvailableChecks:'{known} 回中 {available} 回空室あり', trendPriceRange:'履歴料金 {min} – {max}', trendUpdated:'更新 {time}', trendRecordsDetail:'検索 {count} 回 · {days} 日間',
                trendStatusAvailable:'空室あり', trendStatusUnavailable:'空室なし', trendStatusUnknown:'要確認', trendNoPrice:'料金なし', trendNoRoomType:'部屋タイプ未取得',
                trendPriceAxis:'最低料金', trendAvailabilityAxis:'検索ごとの結果', trendLegendPrice:'最低料金', trendLegendAvailable:'空室あり', trendLegendUnavailable:'空室なし', trendLegendUnknown:'要確認', trendEachBlock:'色ブロック1つが検索1回を表します',
                trendRecentChecks:'最近の検索明細', trendTime:'検索時刻', trendStatus:'状態', trendPrice:'最低料金', trendRooms:'残室', trendRoomType:'部屋タイプ', trendRoomCount:'{count} 室', trendNoHotelHistory:'現在の条件ではこのホテルの履歴がありません',
                homeAvailabilityRate:'直近空室率 {rate}% · 検索 {samples} 回'
              },
              ko: {
                trendScopeCurrent:'현재 숙박일, 인원 및 객실 조건에 맞는 기록만 표시', trendHotel:'호텔', trendRange:'기간', trendDays:'{count}일',
                trendSelectedSummary:'검색 기록 {count}개 · 호텔 {hotels}개', trendCurrentStatus:'현재 상태', trendLatestPrice:'현재 최저가', trendHistoricalRate:'최근 검색 객실 있음 비율', trendDataAmount:'데이터 양',
                trendAvailableChecks:'{known}회 중 {available}회 객실 있음', trendPriceRange:'기록 가격 {min} – {max}', trendUpdated:'업데이트 {time}', trendRecordsDetail:'검색 {count}회 · {days}일 범위',
                trendStatusAvailable:'객실 있음', trendStatusUnavailable:'객실 없음', trendStatusUnknown:'확인 필요', trendNoPrice:'가격 없음', trendNoRoomType:'객실형 정보 없음',
                trendPriceAxis:'최저가', trendAvailabilityAxis:'검색별 결과', trendLegendPrice:'최저가', trendLegendAvailable:'객실 있음', trendLegendUnavailable:'객실 없음', trendLegendUnknown:'확인 필요', trendEachBlock:'색상 블록 하나가 검색 1회를 나타냅니다',
                trendRecentChecks:'최근 검색 상세', trendTime:'검색 시간', trendStatus:'상태', trendPrice:'최저가', trendRooms:'남은 객실', trendRoomType:'객실형', trendRoomCount:'{count}실', trendNoHotelHistory:'현재 조건에 맞는 이 호텔의 기록이 없습니다',
                homeAvailabilityRate:'최근 객실 있음 {rate}% · 검색 {samples}회'
              },
              en: {
                trendScopeCurrent:'Only observations matching the current dates, guests, and room preferences are shown', trendHotel:'Hotel', trendRange:'Range', trendDays:'{count} days',
                trendSelectedSummary:'{count} scan observations · {hotels} hotels', trendCurrentStatus:'Current status', trendLatestPrice:'Current lowest price', trendHistoricalRate:'Recent availability rate', trendDataAmount:'Data volume',
                trendAvailableChecks:'Available in {available} of {known} scans', trendPriceRange:'Historical range {min} – {max}', trendUpdated:'Updated {time}', trendRecordsDetail:'{count} scans · {days}-day range',
                trendStatusAvailable:'Available', trendStatusUnavailable:'Unavailable', trendStatusUnknown:'Check', trendNoPrice:'No current quote', trendNoRoomType:'Room type unavailable',
                trendPriceAxis:'Lowest price', trendAvailabilityAxis:'Result of each scan', trendLegendPrice:'Lowest price', trendLegendAvailable:'Available', trendLegendUnavailable:'Unavailable', trendLegendUnknown:'Check', trendEachBlock:'Each colored block represents one scan',
                trendRecentChecks:'Recent scan details', trendTime:'Scan time', trendStatus:'Status', trendPrice:'Lowest price', trendRooms:'Left', trendRoomType:'Room type', trendRoomCount:'{count} rooms', trendNoHotelHistory:'No history for this hotel under the current conditions',
                homeAvailabilityRate:'Recent availability {rate}% · {samples} scans'
              }
            };
            Object.assign(SINGLE_UI_OVERRIDES.zh_cn, TREND_READABLE_UI.zh_cn);
            Object.assign(SINGLE_UI_OVERRIDES.zh_tw, TREND_READABLE_UI.zh_tw);
            Object.assign(SINGLE_UI_OVERRIDES.ja, TREND_READABLE_UI.ja);
            Object.assign(SINGLE_UI_OVERRIDES.ko, TREND_READABLE_UI.ko);
            Object.assign(EN_UI, TREND_READABLE_UI.en);
            const CJK_TEXT = /[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/;
            function hasEnglishSuffix(value){
              const text = String(value || '');
              const split = text.lastIndexOf(' / ');
              return split >= 0 && !CJK_TEXT.test(text.slice(split + 3));
            }
            function englishValue(value, key){
              if (EN_UI[key] != null) return EN_UI[key];
              const text = String(value || '');
              if (hasEnglishSuffix(text)) return text.slice(text.lastIndexOf(' / ') + 3);
              return text;
            }
            UI18N.en = {};
            Object.keys(UI18N.zh_cn || {}).forEach(key => { UI18N.en[key] = englishValue(UI18N.zh_cn[key], key); });
            Object.assign(UI18N.en, EN_UI);
            Object.assign(UI18N.en, MOBILE_UI18N.en);
            const LANG_OPTION_TEXT = {
              zh_cn: {zh_cn:'中文（简体）', zh_tw:'中文（繁體）', ja:'日语', ko:'韩语', en:'英语'},
              zh_tw: {zh_cn:'中文（簡體）', zh_tw:'中文（繁體）', ja:'日語', ko:'韓語', en:'英語'},
              ja: {zh_cn:'中国語（簡体）', zh_tw:'中国語（繁体）', ja:'日本語', ko:'韓国語', en:'英語'},
              ko: {zh_cn:'중국어(간체)', zh_tw:'중국어(번체)', ja:'일본어', ko:'한국어', en:'영어'},
              en: {zh_cn:'Simplified Chinese', zh_tw:'Traditional Chinese', ja:'Japanese', ko:'Korean', en:'English'}
            };
            function currentLang(){ return document.getElementById('primary_language')?.value || 'zh_cn'; }
            function tx(key){
              const lang = currentLang();
              const override = SINGLE_UI_OVERRIDES[lang]?.[key];
              if (override != null) return override;
              const value = (UI18N[lang] && UI18N[lang][key]) || UI18N.en[key] || UI18N.zh_cn[key] || key;
              if (lang === 'en') return String(value);
              const text = String(value);
              return hasEnglishSuffix(text) ? text.slice(0, text.lastIndexOf(' / ')) : text;
            }
            function fmt(key, values){
              return tx(key).replace(/\{(\w+)\}/g, (_, name) => values && values[name] != null ? String(values[name]) : '');
            }
            const PROVIDER_IDS = ['toyoko', 'routeinn', 'dormy', 'mystays', 'daiwa'];
            const DEFAULT_PROVIDER_IDS = ['toyoko'];
            function providerShort(provider){
              const key = `${PROVIDER_IDS.includes(provider) ? provider : 'toyoko'}Short`;
              return tx(key);
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
            function storageGet(key, fallback=''){
              try { return localStorage.getItem(key) || fallback; } catch(e) { return fallback; }
            }
            function storageSet(key, value){
              try { localStorage.setItem(key, value); } catch(e) {}
            }
            function setSidebarOpen(open){
              document.body.classList.toggle('sidebar-open', !!open);
              const button = document.getElementById('mobile-nav-button');
              const scrim = document.getElementById('sidebar-scrim');
              if (button) button.setAttribute('aria-expanded', open ? 'true' : 'false');
              if (scrim) scrim.hidden = !open;
            }
            function setSidebarCollapsed(collapsed, persist=true){
              const isCollapsed = !!collapsed;
              document.body.classList.toggle('sidebar-collapsed', isCollapsed);
              const button = document.getElementById('sidebar-collapse-button');
              if (button) {
                const label = tx(isCollapsed ? 'expandNav' : 'collapseNav');
                button.textContent = isCollapsed ? '›' : '‹';
                button.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
                button.setAttribute('aria-label', label);
                button.title = label;
              }
              if (persist) storageSet(SIDEBAR_COLLAPSED_KEY, isCollapsed ? '1' : '0');
              setTimeout(() => {
                try { AREA_SELECTED_MAP?.invalidateSize(); } catch(e) {}
                try { HOTEL_INFO_MAP?.invalidateSize(); } catch(e) {}
              }, 240);
            }
            function switchAppView(view, options={}){
              const next = APP_VIEWS.includes(view) ? view : 'home';
              ACTIVE_APP_VIEW = next;
              document.querySelectorAll('.app-view').forEach(panel => {
                const active = panel.dataset.view === next;
                panel.hidden = !active;
                panel.classList.toggle('active', active);
              });
              document.querySelectorAll('[data-app-view]').forEach(button => {
                const active = button.dataset.appView === next;
                button.classList.toggle('active', active);
                if (active) button.setAttribute('aria-current', 'page');
                else button.removeAttribute('aria-current');
              });
              if (options.persist !== false) storageSet(APP_VIEW_KEY, next);
              setSidebarOpen(false);
              if (next === 'search-settings' || next === 'push-settings') {
                const details = document.querySelector(`#view-${next} details.settings-panel`);
                if (details) setDetailsOpen(details, true);
              }
              if (next === 'search') {
                setDetailsOpen(document.getElementById('search_panel'), true);
              }
              if (next === 'home') {
                if (LAST_HOME_PAYLOAD) renderHomeDashboard(LAST_HOME_PAYLOAD);
                refreshHomeInsights(true);
              }
              setTimeout(() => {
                try { AREA_SELECTED_MAP?.invalidateSize(); } catch(e) {}
              }, 60);
              if (options.focus === true) {
                const heading = document.querySelector(`#view-${next} .view-header h1`);
                if (heading) {
                  heading.tabIndex = -1;
                  heading.focus({preventScroll:true});
                }
              }
              if (options.scroll !== false) window.scrollTo({top:0, behavior:options.instant ? 'auto' : 'smooth'});
            }
            function systemTheme(){
              return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            }
            function applyTheme(preference, persist=true){
              THEME_PREFERENCE = ['system','light','dark'].includes(preference) ? preference : 'system';
              const resolved = THEME_PREFERENCE === 'system' ? systemTheme() : THEME_PREFERENCE;
              document.body.dataset.theme = resolved;
              document.body.dataset.themePreference = THEME_PREFERENCE;
              document.querySelectorAll('[data-theme-choice]').forEach(button => {
                const active = button.dataset.themeChoice === THEME_PREFERENCE;
                button.classList.toggle('active', active);
                button.setAttribute('aria-pressed', active ? 'true' : 'false');
              });
              const toggle = document.getElementById('theme-toggle-button');
              if (toggle) {
                toggle.textContent = resolved === 'dark' ? '☼' : '◐';
                toggle.setAttribute('aria-label', `${tx('theme')}: ${resolved}`);
                toggle.title = `${tx('theme')}: ${resolved}`;
              }
              if (persist) storageSet(THEME_KEY, THEME_PREFERENCE);
              setTimeout(() => {
                try { AREA_SELECTED_MAP?.invalidateSize(); } catch(e) {}
                try { HOTEL_INFO_MAP?.invalidateSize(); } catch(e) {}
              }, 60);
            }
            function openHomeQuickAction(action){
              if (action === 'push') {
                switchAppView('push-settings');
                return;
              }
              switchAppView('search');
              setDetailsOpen(document.getElementById('search_panel'), true);
              if (action === 'history') {
                const history = document.getElementById('search_history_panel');
                if (history) {
                  setDetailsOpen(history, true);
                  setTimeout(() => history.scrollIntoView({behavior:'smooth', block:'center'}), 80);
                }
                return;
              }
              const mode = action === 'radius' ? 'radius' : 'area';
              const radio = document.querySelector(`input[name="hotel_picker_mode"][value="${mode}"]`);
              if (radio) {
                radio.checked = true;
                radio.dispatchEvent(new Event('change', {bubbles:true}));
              }
              setTimeout(() => document.getElementById(mode === 'radius' ? 'radius_query' : 'area_region')?.focus(), 100);
            }
            function setLanguageMenuOpen(open){
              const menu = document.getElementById('language-menu');
              const button = document.getElementById('language-menu-button');
              if (menu) menu.hidden = !open;
              if (button) button.setAttribute('aria-expanded', open ? 'true' : 'false');
            }
            function guideAppVersion(){
              return document.body.dataset.appVersion || 'development';
            }
            function guideSteps(){
              return [1,2,3,4,5].map(number => ({
                title: tx(`guideStep${number}Title`),
                body: tx(`guideStep${number}Body`),
                tip: tx(`guideStep${number}Tip`)
              }));
            }
            function renderGuideStep(){
              const steps = guideSteps();
              GUIDE_STEP = Math.max(0, Math.min(GUIDE_STEP, steps.length - 1));
              const step = steps[GUIDE_STEP];
              const set = (id, value) => {
                const element = document.getElementById(id);
                if (element) element.textContent = value;
              };
              set('guide-title', tx('guideTitle'));
              set('guide-step-count', `${GUIDE_STEP + 1} / ${steps.length}`);
              set('guide-step-title', step.title);
              set('guide-step-body', step.body);
              set('guide-step-tip', step.tip);
              set('guide-skip-button', tx('guideSkip'));
              set('guide-prev-button', tx('guideBack'));
              set('guide-next-button', GUIDE_STEP === steps.length - 1 ? tx('guideFinish') : tx('guideNext'));
              document.querySelectorAll('[data-guide-visual]').forEach((visual, index) => {
                const active = index === GUIDE_STEP;
                visual.hidden = !active;
                visual.classList.toggle('active', active);
              });
              document.querySelectorAll('[data-guide-jump]').forEach((button, index) => {
                const active = index === GUIDE_STEP;
                button.classList.toggle('active', active);
                if (active) button.setAttribute('aria-current', 'step');
                else button.removeAttribute('aria-current');
                button.setAttribute('aria-label', `${index + 1}: ${steps[index].title}`);
              });
              const progress = document.getElementById('guide-progress');
              if (progress) progress.setAttribute('aria-label', tx('guideProgress'));
              const previous = document.getElementById('guide-prev-button');
              if (previous) previous.disabled = GUIDE_STEP === 0;
            }
            function openGuide(automatic=false){
              const modal = document.getElementById('guide-modal');
              if (!modal) return;
              GUIDE_AUTO_OPEN = !!automatic;
              GUIDE_STEP = 0;
              renderGuideStep();
              modal.hidden = false;
              document.body.classList.add('guide-open');
              setSidebarOpen(false);
              setTimeout(() => document.getElementById('guide-next-button')?.focus(), 60);
            }
            function closeGuide(){
              const modal = document.getElementById('guide-modal');
              if (!modal || modal.hidden) return;
              modal.hidden = true;
              document.body.classList.remove('guide-open');
              storageSet(GUIDE_SEEN_KEY, guideAppVersion());
              const shouldRestoreFocus = !GUIDE_AUTO_OPEN;
              GUIDE_AUTO_OPEN = false;
              if (shouldRestoreFocus) document.getElementById('guide-open-button')?.focus();
            }
            function openUpdateDialog(automatic=false){
              const modal = document.getElementById('update-modal');
              if (!modal) return;
              UPDATE_DIALOG_AUTO_OPEN = !!automatic;
              modal.hidden = false;
              document.body.classList.add('update-open');
              setSidebarOpen(false);
              renderUpdateDialog(LAST_UPDATE_STATUS || {
                state:'idle',
                current_version:document.body.dataset.appVersion || '-'
              });
              refreshUpdateStatus();
              setTimeout(() => {
                const target = document.getElementById('btn_upgrade');
                if (target && !target.disabled) target.focus();
                else document.getElementById('btn_update_check')?.focus();
              }, 60);
            }
            function closeUpdateDialog(){
              const modal = document.getElementById('update-modal');
              if (!modal || modal.hidden) return;
              modal.hidden = true;
              document.body.classList.remove('update-open');
              const shouldRestoreFocus = !UPDATE_DIALOG_AUTO_OPEN;
              UPDATE_DIALOG_AUTO_OPEN = false;
              if (shouldRestoreFocus) document.getElementById('update-open-button')?.focus();
            }
            function initAppShell(){
              const requestedView = new URLSearchParams(window.location.search).get('view');
              const storedView = APP_VIEWS.includes(requestedView) ? requestedView : 'home';
              const storedLanguage = storageGet(LANGUAGE_KEY, '');
              const languageSelect = document.getElementById('primary_language');
              if (languageSelect && ['zh_cn','zh_tw','ja','ko','en'].includes(storedLanguage)) languageSelect.value = storedLanguage;
              setSidebarCollapsed(storageGet(SIDEBAR_COLLAPSED_KEY, '0') === '1', false);
              THEME_PREFERENCE = storageGet(THEME_KEY, 'system');
              applyTheme(THEME_PREFERENCE, false);
              switchAppView(storedView, {persist:false, focus:false, scroll:false, instant:true});
              document.querySelectorAll('[data-app-view]').forEach(button => {
                button.addEventListener('click', () => switchAppView(button.dataset.appView));
              });
              document.querySelectorAll('[data-home-nav]').forEach(button => {
                button.addEventListener('click', () => switchAppView(button.dataset.homeNav || 'home'));
              });
              document.getElementById('home-primary-action')?.addEventListener('click', () => switchAppView(LAST_RUNNING ? 'monitor' : 'search'));
              document.getElementById('home-secondary-action')?.addEventListener('click', () => switchAppView('monitor'));
              document.getElementById('home-edit-search')?.addEventListener('click', () => switchAppView('search'));
              document.getElementById('home-view-results')?.addEventListener('click', () => switchAppView('monitor'));
              document.getElementById('home-events-more')?.addEventListener('click', () => {
                switchAppView('monitor');
                const panel = document.getElementById('event-center-panel');
                if (panel) setDetailsOpen(panel, true);
                refreshEventCenter();
              });
              document.getElementById('home-trend-more')?.addEventListener('click', () => {
                switchAppView('monitor');
                const panel = document.getElementById('trend-panel');
                if (panel) setDetailsOpen(panel, true);
                refreshTrends(true);
              });
              document.querySelectorAll('[data-home-quick]').forEach(button => {
                button.addEventListener('click', () => openHomeQuickAction(button.dataset.homeQuick || 'area'));
              });
              document.getElementById('mobile-nav-button')?.addEventListener('click', () => {
                setSidebarOpen(!document.body.classList.contains('sidebar-open'));
              });
              document.getElementById('sidebar-collapse-button')?.addEventListener('click', () => {
                setSidebarCollapsed(!document.body.classList.contains('sidebar-collapsed'));
              });
              document.getElementById('sidebar-scrim')?.addEventListener('click', () => setSidebarOpen(false));
              document.getElementById('language-menu-button')?.addEventListener('click', event => {
                event.stopPropagation();
                const menu = document.getElementById('language-menu');
                setLanguageMenuOpen(!!menu?.hidden);
              });
              document.querySelectorAll('[data-language]').forEach(button => {
                button.addEventListener('click', () => {
                  const select = document.getElementById('primary_language');
                  if (select) {
                    select.value = button.dataset.language || 'zh_cn';
                    select.dispatchEvent(new Event('change', {bubbles:true}));
                  }
                  setLanguageMenuOpen(false);
                });
              });
              document.getElementById('theme-toggle-button')?.addEventListener('click', () => {
                applyTheme(document.body.dataset.theme === 'dark' ? 'light' : 'dark');
              });
              document.getElementById('guide-open-button')?.addEventListener('click', () => openGuide(false));
              document.getElementById('update-open-button')?.addEventListener('click', () => openUpdateDialog(false));
              document.getElementById('btn_mobile_access_apply')?.addEventListener('click', () => saveMobileAccess(false));
              document.getElementById('btn_mobile_access_rotate')?.addEventListener('click', () => saveMobileAccess(true));
              document.getElementById('btn_mobile_access_copy')?.addEventListener('click', copyMobileAccessUrl);
              document.querySelectorAll('[data-mobile-connection]').forEach(button => {
                button.addEventListener('click', () => selectMobileConnection(button.dataset.mobileConnection || 'lan'));
              });
              document.getElementById('mobile_access_url')?.addEventListener('input', event => {
                if (MOBILE_CONNECTION_MODE !== 'public') return;
                const value = String(event.target?.value || '').trim();
                const openLink = document.getElementById('btn_mobile_access_open');
                if (openLink) {
                  openLink.href = value || '#';
                  openLink.setAttribute('aria-disabled', value ? 'false' : 'true');
                }
              });
              document.getElementById('update-close-button')?.addEventListener('click', closeUpdateDialog);
              document.getElementById('update-modal')?.addEventListener('click', event => {
                if (event.target === event.currentTarget) closeUpdateDialog();
              });
              document.getElementById('guide-close-button')?.addEventListener('click', closeGuide);
              document.getElementById('guide-skip-button')?.addEventListener('click', closeGuide);
              document.getElementById('guide-prev-button')?.addEventListener('click', () => {
                GUIDE_STEP -= 1;
                renderGuideStep();
              });
              document.getElementById('guide-next-button')?.addEventListener('click', () => {
                if (GUIDE_STEP >= guideSteps().length - 1) closeGuide();
                else {
                  GUIDE_STEP += 1;
                  renderGuideStep();
                }
              });
              document.querySelectorAll('[data-guide-jump]').forEach(button => {
                button.addEventListener('click', () => {
                  GUIDE_STEP = Number(button.dataset.guideJump || 0);
                  renderGuideStep();
                });
              });
              document.querySelectorAll('[data-theme-choice]').forEach(button => {
                button.addEventListener('click', () => applyTheme(button.dataset.themeChoice || 'system'));
              });
              document.addEventListener('click', event => {
                if (!event.target.closest?.('.language-menu-wrap')) setLanguageMenuOpen(false);
              });
              window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', () => {
                if (THEME_PREFERENCE === 'system') applyTheme('system', false);
              });
              document.addEventListener('keydown', event => {
                if (event.key !== 'Escape') return;
                if (!document.getElementById('update-modal')?.hidden) closeUpdateDialog();
                else if (!document.getElementById('guide-modal')?.hidden) closeGuide();
              });
              setTimeout(() => {
                if (storageGet(GUIDE_SEEN_KEY, '') !== guideAppVersion()) openGuide(true);
              }, 450);
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
              return currentLang() === 'en' ? (e || p) : (p || e);
            }
            function localizedAreaParts(item){
              if (!item) return {primary:'', en:''};
              const lang = currentLang();
              const en = item.name || '';
              if (lang === 'en') return {primary:en, en};
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
              if (lang === 'en') return `All of ${e}`;
              const allPrimary = lang === 'ja' ? `すべての ${p || e}` : lang === 'ko' ? `${p || e} 전체` : `全部 ${p || e}`;
              return allPrimary;
            }
            function channelName(key, fallback){
              const map = {telegram:'telegramName', local:'localName', email:'emailName', bark:'barkName', serverchan:'serverChanName'};
              return map[key] ? tx(map[key]) : (fallback || key);
            }
            function historyAreaFallback(kind, value){
              if (kind === 'region') {
                if (!value) return tx('historyNoRegion');
                const region = (AREA_INDEX?.regions || []).find(item => String(item.id) === String(value));
                return region ? localizedAreaLabel(region) : String(value);
              }
              if (!value) return tx('historyAllAreas');
              const raw = String(value);
              const regions = AREA_INDEX?.regions || [];
              if (raw.startsWith('pref-')) {
                const prefId = raw.slice(5);
                const pref = regions.flatMap(region => region.prefectures || [])
                  .find(item => String(item.id) === prefId);
                if (pref) {
                  const parts = localizedAreaParts(pref);
                  return allOfLabel(parts.primary, parts.en || pref.name);
                }
              }
              if (raw.startsWith('area-')) {
                const areaId = raw.slice(5);
                for (const region of regions) {
                  for (const pref of region.prefectures || []) {
                    const area = (pref.areas || []).find(item => String(item.id) === areaId);
                    if (area) return `${localizedAreaLabel(pref)} - ${localizedAreaLabel(area)}`;
                  }
                }
              }
              return raw;
            }
            function applyUiLanguage(){
              const lang = currentLang();
              document.title = tx('appName');
              setNodeText('.topbar h2', tx('appName'));
              setNodeText('.sidebar-brand strong', tx('appName'));
              setNodeText('.sidebar-brand div > span', tx('workspace'));
              setLabelFor('primary_language', tx('language'));
              const navLabels = document.querySelectorAll('.sidebar-nav .nav-label');
              [tx('navHome'), tx('navSearch'), tx('navMonitor'), tx('searchSettings'), tx('pushSettings')]
                .forEach((text, idx) => {
                  if (navLabels[idx]) navLabels[idx].textContent = text;
                  const button = navLabels[idx]?.closest('.sidebar-nav-item');
                  if (button) button.title = text;
                });
              const interfaceSettingsButton = document.getElementById('interface-settings-button');
              if (interfaceSettingsButton) {
                interfaceSettingsButton.setAttribute('aria-label', tx('interfaceSettings'));
                interfaceSettingsButton.title = tx('interfaceSettings');
              }
              [
                ['#home-eyebrow','homeEyebrow'], ['#home-greeting','homeGreeting'],
                ['#home-live-label','homeLiveLabel'], ['#home-next-label','homeNextScan'],
                ['#home-metric-status-label','homeMetricStatus'], ['#home-metric-available-label','homeMetricAvailable'],
                ['#home-metric-hotels-label','homeMetricHotels'], ['#home-metric-next-label','homeMetricNext'], ['#home-metric-traffic-label','homeMetricTraffic'],
                ['#home-task-kicker','homeTaskKicker'], ['#home-checkin-label','homeCheckin'], ['#home-checkout-label','homeCheckout'],
                ['#home-edit-search','homeEditSearch'], ['#home-view-results','homeViewResults'],
                ['#home-activity-kicker','homeActivityKicker'], ['#home-activity-title','homeActivityTitle'], ['#home-events-more','homeAllEvents'],
                ['#home-trend-kicker','homeTrendKicker'], ['#home-trend-title','homeTrendTitle'], ['#home-trend-more','homeViewTrend'], ['#home-trend-observations-label','homeTrendRecords'],
                ['#home-quick-kicker','homeQuickKicker'], ['#home-quick-title','homeQuickTitle'],
                ['#home-quick-area','homeQuickArea'], ['#home-quick-radius','homeQuickRadius'], ['#home-quick-history','homeQuickHistory'], ['#home-quick-push','homeQuickPush'],
                ['#home-health-kicker','homeHealthKicker'], ['#home-health-title','homeHealthTitle'],
                ['#home-health-connection-label','homeConnection'], ['#home-health-providers-label','homeProviders'],
                ['#home-health-notifications-label','homeNotifications'], ['#home-health-data-label','homeHistoryData']
              ].forEach(([selector,key]) => setNodeText(selector, tx(key)));
              if (LAST_HOME_PAYLOAD) renderHomeDashboard(LAST_HOME_PAYLOAD);
              const viewHeaders = document.querySelectorAll('.app-view > .view-header');
              const viewTitles = [tx('navHome'), tx('navSearch'), tx('navMonitor'), tx('searchSettings'), tx('pushSettings'), tx('interfaceSettings')];
              const viewHelp = ['', tx('searchViewHelp'), tx('monitorViewHelp'), tx('searchSettingsViewHelp'), tx('pushSettingsViewHelp'), tx('interfaceViewHelp')];
              viewHeaders.forEach((header, idx) => {
                const title = header.querySelector('h1');
                const help = header.querySelector('p');
                if (title && viewTitles[idx]) title.textContent = viewTitles[idx];
                if (help && viewHelp[idx]) help.textContent = viewHelp[idx];
              });
              const interfaceCards = document.querySelectorAll('.interface-card');
              if (interfaceCards[0]) {
                const title = interfaceCards[0].querySelector('h2');
                const help = interfaceCards[0].querySelector('p');
                if (title) title.textContent = tx('language');
                if (help) help.textContent = tx('languageHelp');
              }
              if (interfaceCards[1]) {
                const title = interfaceCards[1].querySelector('h2');
                const help = interfaceCards[1].querySelector('p');
                if (title) title.textContent = tx('theme');
                if (help) help.textContent = tx('themeHelp');
              }
              setNodeText('#mobile-access-title', tx('mobileAccessTitle'));
              setNodeText('#mobile-access-help', tx('mobileAccessHelp'));
              setNodeText('#mobile-access-enable-label', tx('enableMobileAccess'));
              setNodeText('#btn_mobile_access_apply', tx('mobileApply'));
              setNodeText('#mobile-access-url-label', tx('mobileAddress'));
              setNodeText('#mobile-access-code-label', tx('pairingCode'));
              setNodeText('#btn_mobile_access_copy', tx('copy'));
              setNodeText('#btn_mobile_access_rotate', tx('rotate'));
              setNodeText('#mobile-access-method-title', tx('mobileChooseConnection'));
              setNodeText('#mobile-lan-title', tx('mobileLanTitle'));
              setNodeText('#mobile-lan-help', tx('mobileLanHelp'));
              setNodeText('#mobile-tailscale-title', tx('mobileTailscaleTitle'));
              setNodeText('#mobile-tailscale-help', tx('mobileTailscaleHelp'));
              setNodeText('#mobile-public-title', tx('mobilePublicTitle'));
              setNodeText('#mobile-public-help', tx('mobilePublicHelp'));
              setNodeText('#mobile-step-network', tx('mobileStepNetwork'));
              setNodeText('#mobile-step-scan', tx('mobileStepScan'));
              setNodeText('#mobile-step-pair', tx('mobileStepPair'));
              const mobileOpen = document.getElementById('btn_mobile_access_open');
              if (mobileOpen) {
                mobileOpen.setAttribute('aria-label', tx('mobileOpen'));
                mobileOpen.title = tx('mobileOpen');
              }
              setNodeText('#mobile-access-note', tx('mobileNote'));
              setNodeText('#mobile-access-qr-label', tx('mobileQr'));
              if (LAST_MOBILE_ACCESS_STATUS) renderMobileAccess(LAST_MOBILE_ACCESS_STATUS);
              const themeButtons = document.querySelectorAll('[data-theme-choice]');
              [tx('themeSystem'), tx('themeLight'), tx('themeDark')].forEach((text, idx) => {
                if (themeButtons[idx]) themeButtons[idx].textContent = text;
              });
              document.querySelectorAll('[data-language]').forEach(button => {
                button.setAttribute('aria-checked', button.dataset.language === lang ? 'true' : 'false');
                button.classList.toggle('active', button.dataset.language === lang);
              });
              const languageButton = document.getElementById('language-menu-button');
              if (languageButton) {
                languageButton.setAttribute('aria-label', tx('language'));
                languageButton.title = tx('language');
              }
              const guideButton = document.getElementById('guide-open-button');
              if (guideButton) {
                guideButton.setAttribute('aria-label', tx('guideOpen'));
                guideButton.title = tx('guideOpen');
              }
              const updateButton = document.getElementById('update-open-button');
              if (updateButton) {
                updateButton.setAttribute('aria-label', tx('updateOpen'));
                updateButton.title = tx('updateOpen');
              }
              const updateClose = document.getElementById('update-close-button');
              if (updateClose) {
                updateClose.setAttribute('aria-label', tx('updateClose'));
                updateClose.title = tx('updateClose');
              }
              const guideClose = document.getElementById('guide-close-button');
              if (guideClose) {
                guideClose.setAttribute('aria-label', tx('guideClose'));
                guideClose.title = tx('guideClose');
              }
              renderGuideStep();
              setNodeText('#update-dialog-kicker', tx('updateDialogKicker'));
              setNodeText('#update-dialog-title', tx('updateDialogTitle'));
              setNodeText('#update-app-name', tx('appName'));
              setNodeText('#update-current-label', tx('currentVersionLabel'));
              setNodeText('#update-latest-label', tx('latestVersionLabel'));
              document.querySelector('.update-version-grid')?.setAttribute('aria-label', tx('versionInformation'));
              setNodeText('#update-author-label', tx('authorLabel'));
              setNodeText('#update-github-label', tx('githubLabel'));
              setNodeText('#btn_update_check', tx('checkAgain'));
              setSidebarCollapsed(document.body.classList.contains('sidebar-collapsed'), false);
              applyTheme(THEME_PREFERENCE, false);
              setNodeText('#run_settings_legend', tx('runSettings'));
              setNodeText('#search_panel > summary', tx('search'));
              setNodeText('.search-title', tx('searchTitle'));
              setNodeText('.search-subtitle', tx('searchSubtitle'));
              setNodeText('#btn_today', tx('tonight'));
              setNodeText('#btn_tomorrow', tx('tomorrow'));
              setNodeText('#btn_weekend', tx('weekend'));
              setNodeText('.quick-date-field > label', tx('quickDates'));
              setLabelFor('start_date', tx('checkin'));
              setLabelFor('end_date', tx('checkout'));
              setLabelFor('people', tx('people'));
              setLabelFor('rooms', tx('rooms'));
              setLabelFor('smoking', tx('smoking'));
              setLabelFor('room_requirement', tx('roomType'));
              setLabelFor('membership_status', tx('membership'));
              document.querySelectorAll('[data-step-target="people"]').forEach(button => {
                button.setAttribute('aria-label', tx(button.dataset.stepDelta === '-1' ? 'decreasePeople' : 'increasePeople'));
              });
              document.querySelectorAll('[data-step-target="rooms"]').forEach(button => {
                button.setAttribute('aria-label', tx(button.dataset.stepDelta === '-1' ? 'decreaseRooms' : 'increaseRooms'));
              });
              setNodeText('.provider-selector-title', tx('hotelBrands'));
              ['toyoko','routeinn','dormy','mystays','daiwa'].forEach(provider => {
                const label = document.getElementById(`provider_${provider}`)?.closest('.provider-choice')?.querySelector('span');
                if (label) label.textContent = tx(`${provider}Provider`);
              });
              setNodeText('#btn_provider_all', tx('allBrands'));
              setInlineLabel('#hotel_picker_mode_tabs label:nth-child(1)', tx('areaMode'));
              setInlineLabel('#hotel_picker_mode_tabs label:nth-child(2)', tx('radiusMode'));
              setLabelFor('area_region', tx('region'));
              setLabelFor('area_detail', tx('detailArea'));
              setLabelFor('radius_query', tx('placeAddressCoordinates'));
              const radiusLabel = document.querySelector('label[for="radius_km"]');
              if (radiusLabel) radiusLabel.innerHTML = `${escText(tx('radius'))} <b><span id="radius_km_val">${escText(document.getElementById('radius_km')?.value || '')}</span> km</b>`;
              const radiusQuery = document.getElementById('radius_query');
              if (radiusQuery) radiusQuery.placeholder = tx('radiusPlaceholder');
              setNodeText('#btn_radius_load', tx('loadNearby'));
              setNodeText('#btn_area_load', tx('loadHotels'));
              setNodeText('#btn_area_all', tx('selectAll'));
              setNodeText('#btn_area_none', tx('selectNone'));
              setNodeText('#btn_area_selected_only', tx('selectedOnly'));
              const sortLabel = document.querySelector('.hotel-sort-control > span');
              if (sortLabel) sortLabel.textContent = tx('sort');
              setSelectOptions('area_sort', {
                default:tx('sortDefault'), distance:tx('sortDistance'), name:tx('sortName'), code:tx('sortCode')
              });
              const workspaceTabs = document.querySelectorAll('[data-hotel-workspace-view]');
              if (workspaceTabs[0]) workspaceTabs[0].textContent = tx('listView');
              if (workspaceTabs[1]) workspaceTabs[1].textContent = tx('mapView');
              setNodeText('#btn_catalog_refresh', tx('catalogRefresh'));
              setNodeText('#btn_catalog_ack', tx('catalogAcknowledge'));
              setNodeText('.selected-map-title', tx('selectedHotelMap'));
              const mapStatus = document.getElementById('area_map_status');
              if (mapStatus && !(Array.isArray(AREA_HOTELS) && AREA_HOTELS.length)) mapStatus.textContent = tx('selectedHotelMapHint');
              renderHotelCatalog(LAST_CATALOG_STATUS);
              renderProviderCatalog(LAST_PROVIDER_CATALOG_STATUS);
              const areaFilter = document.getElementById('area_filter');
              if (areaFilter) areaFilter.placeholder = tx('filterPlaceholder');
              syncProviderAllButton();
              const historySummary = document.querySelector('#search_history_panel > summary');
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
              setCheckboxLabel('adaptive_backoff_enabled', tx('adaptiveBackoff'));
              const cadenceCard = document.querySelectorAll('.settings-card')[2];
              if (cadenceCard) {
                const labels = cadenceCard.querySelectorAll('label');
                [tx('roundInterval'), tx('perHotelDelay'), tx('requestJitter')].forEach((text, idx)=>{ if(labels[idx]) labels[idx].textContent=text; });
                const backoffHelp = cadenceCard.querySelector('.adaptive-backoff-help');
                if (backoffHelp) backoffHelp.textContent = tx('adaptiveBackoffHelp');
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
              document.querySelectorAll('.settings-card .help, #radius_mode_panel .radius-grid .help').forEach(help => {
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
              setNodeText('#diagnostics-title', tx('diagnosticsTitle'));
              setNodeText('#diagnostics-summary', tx('diagnosticsSummary'));
              setNodeText('#diagnostics-throughput-label', tx('diagnosticsThroughput'));
              setNodeText('#diagnostics-eta-label', tx('diagnosticsEta'));
              setNodeText('#diagnostics-queue-label', tx('diagnosticsQueue'));
              setNodeText('#diagnostics-latency-label', tx('diagnosticsLatency'));
              setNodeText('#diagnostics-priority-label', tx('diagnosticsPriority'));
              setNodeText('#diagnostics-protection-label', tx('diagnosticsProtection'));
              setNodeText('#diagnostics-cache-label', tx('diagnosticsCache'));
              setNodeText('#diagnostics-saved-label', tx('diagnosticsSaved'));
              setNodeText('#btn_cache_clear', tx('clearCache'));
              setNodeText('#trend-panel-title', tx('trendTitle'));
              setNodeText('#trend-scope-note', tx('trendScopeCurrent'));
              setNodeText('#trend-hotel-label', tx('trendHotel'));
              setNodeText('#trend-range-label', tx('trendRange'));
              document.querySelectorAll('#trend_days option').forEach(option => {
                option.textContent = fmt('trendDays', {count:option.value});
              });
              setNodeText('#btn_trend_refresh', tx('refresh'));
              if (LAST_TREND_DATA) renderTrends(LAST_TREND_DATA);
              setNodeText('#pwa-title', tx('pwaTitle'));
              setNodeText('#pwa-help', tx('pwaHelp'));
              setNodeText('#btn_pwa_install', tx('pwaInstall'));
              setNodeText('#provider-matrix-title', tx('providerMatrixTitle'));
              setNodeText('#provider-matrix-help', tx('providerMatrixHelp'));
              setNodeText('#simulation-title', tx('simulationTitle'));
              setNodeText('#simulation-help', tx('simulationHelp'));
              setNodeText('#btn_simulation_run', tx('simulationRun'));
              setNodeText('#event-center-title', tx('eventCenterTitle'));
              setAllText('.metric > span', [tx('status'), tx('loop'), tx('progress'), tx('uptime')]);
              setNodeText('#snapshot-dates-label', tx('dates'));
              setNodeText('#snapshot-hotels-label', tx('snapshotHotels'));
              setNodeText('#snapshot-engine-label', tx('engineSummary'));
              setNodeText('#snapshot-cadence-label', tx('roundSummary'));
              setNodeText('#snapshot-safety-label', tx('safety'));
              setAllText('.result-stat span', [tx('available'), tx('unavailable'), tx('check'), tx('total')]);
              setAllText('.result-table:not(.result-log-table) th', [tx('code'), tx('hotel'), tx('status'), tx('minPrice'), tx('left'), tx('roomType')]);
              setAllText('.result-log-table th', [tx('code'), tx('hotel'), tx('availableSince'), tx('duration'), tx('minPrice'), tx('roomType')]);
              setNodeText('.push-subtitle', tx('pushSubtitle'));
              setNodeText('#btn_scan_once', tx('scanOnce'));
              setNodeText('#btn_start', LAST_RUNNING ? tx('restart') : tx('start'));
              setNodeText('#btn_stop', tx('stop'));
              setNodeText('#btn_default', tx('defaults'));
              setNodeText('#btn_local_test', tx('testNotification'));
              const resultFilterButtons = document.querySelectorAll('[data-result-filter]');
              [tx('allFilter'), tx('available'), tx('unavailable'), tx('check'), tx('changesFilter')].forEach((text, idx) => {
                if (resultFilterButtons[idx]) resultFilterButtons[idx].textContent = text;
              });
              const resultQuery = document.getElementById('result_query');
              if (resultQuery) resultQuery.placeholder = tx('resultSearchPlaceholder');
              setNodeText('#btn_results_refresh', tx('refreshResults'));
              setNodeText('#btn_results_export', tx('exportResults'));
              setLabelFor('result_query', tx('resultTitle'));
              setLabelFor('results_sort', tx('sort'));
              setSelectOptions('results_sort', {
                default: tx('sortDefault'), status: tx('sortStatus'), price: tx('sortPrice'),
                name: tx('sortName'), distance: tx('sortDistance')
              });
              const langLabels = LANG_OPTION_TEXT[lang] || LANG_OPTION_TEXT.zh_cn;
              setSelectOptions('primary_language', langLabels);
              const localizedOptions = ({
                zh_cn:{noSmoking:'无烟房',Smoking:'吸烟房',all:'不限制',any:'不限制',single:'单人房',double:'大床房',twin:'双床房',member:'会员',non_member:'非会员',unknown:'未知',http:'HTTP/API（推荐轻量）',playwright:'Playwright（兼容模式）'},
                zh_tw:{noSmoking:'禁菸房',Smoking:'吸菸房',all:'不限制',any:'不限制',single:'單人房',double:'雙人床房',twin:'雙床房',member:'會員',non_member:'非會員',unknown:'未知',http:'HTTP/API（推薦輕量）',playwright:'Playwright（相容模式）'},
                ja:{noSmoking:'禁煙',Smoking:'喫煙',all:'指定なし',any:'指定なし',single:'シングル',double:'ダブル',twin:'ツイン',member:'会員',non_member:'非会員',unknown:'不明',http:'HTTP/API（推奨・軽量）',playwright:'Playwright（互換性重視）'},
                ko:{noSmoking:'금연',Smoking:'흡연',all:'제한 없음',any:'제한 없음',single:'싱글',double:'더블',twin:'트윈',member:'회원',non_member:'비회원',unknown:'알 수 없음',http:'HTTP/API (권장, 경량)',playwright:'Playwright (호환성 우선)'},
                en:{noSmoking:'Non-Smoking',Smoking:'Smoking',all:'Any',any:'Any',single:'Single',double:'Double',twin:'Twin',member:'Member',non_member:'Non-member',unknown:'Unknown',http:'HTTP/API (recommended, lightweight)',playwright:'Playwright (compatibility mode)'}
              })[lang] || {};
              setSelectOptions('smoking', {
                noSmoking: localizedOptions.noSmoking, Smoking: localizedOptions.Smoking, all: localizedOptions.all
              });
              setSelectOptions('room_requirement', {
                any: localizedOptions.any, single: localizedOptions.single, double: localizedOptions.double, twin: localizedOptions.twin
              });
              setSelectOptions('membership_status', {
                member: localizedOptions.member, non_member: localizedOptions.non_member, unknown: localizedOptions.unknown
              });
              setSelectOptions('engine', {
                http: localizedOptions.http, playwright: localizedOptions.playwright
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
              renderUpdateDialog(LAST_UPDATE_STATUS || null);
              if (Array.isArray(AREA_HOTELS)) renderAreaHotels();
              if (typeof updateAreaSelectionSummary === 'function') updateAreaSelectionSummary();
              setConfigDirty(FORM_DIRTY);
              setConnectionOnline(CONNECTION_ONLINE);
              setRunning(LAST_RUNNING);
              if (LAST_PROGRESS_STATE) renderProgress(LAST_PROGRESS_STATE);
              else {
                setNodeText('#snapshot-safety', tx('safetyNormal'));
                setNodeText('#prog-text', `${tx('progressText')}: 0 / 0 (0%)`);
                setNodeText('#time-text', `${tx('loopElapsed')}: 0s | ${tx('uptime')}: 0s`);
                setNodeText('#action-text', `${tx('currentAction')}: (idle)`);
              }
              renderProviderHealth(LAST_PROVIDER_HEALTH);
              renderDiagnostics(LAST_DIAGNOSTICS);
              setNodeText('.result-log-table .empty-results', tx('noLog'));
              updateResultsTimestamp();
              if (Array.isArray(LAST_RESULTS)) renderRows();
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
              const safety = document.getElementById('snapshot-safety');
              if (safety) {
                const multiplier = Math.max(1, Number(p.backoff_multiplier || 1));
                const ratio = Math.max(0, Number(p.unknown_ratio_percent || 0));
                safety.textContent = multiplier > 1
                  ? fmt('safetyBackoff', {multiplier, ratio})
                  : tx('safetyNormal');
                safety.className = multiplier > 1 ? 'safety-backoff' : 'safety-normal';
                safety.title = p.effective_interval_sec
                  ? `${Number(p.effective_interval_sec)}s`
                  : '';
              }
              if (waiting && waitTotal > 0) startProgressSmoothing();
            }

            function renderProviderHealth(health){
              const container = document.getElementById('provider-health');
              if (!container) return;
              LAST_PROVIDER_HEALTH = health && typeof health === 'object' ? health : {};
              const preferredOrder = ['toyoko', 'routeinn', 'dormy', 'mystays', 'daiwa'];
              const providers = Object.keys(LAST_PROVIDER_HEALTH).sort((left, right) => {
                const leftRank = preferredOrder.indexOf(left);
                const rightRank = preferredOrder.indexOf(right);
                return (leftRank < 0 ? 99 : leftRank) - (rightRank < 0 ? 99 : rightRank);
              });
              if (!providers.length) {
                container.hidden = true;
                container.innerHTML = '';
                return;
              }
              const stateLabels = {
                idle: tx('healthIdle'),
                healthy: tx('healthHealthy'),
                degraded: tx('healthDegraded'),
                cooldown: tx('healthCooldown')
              };
              const chips = providers.map(provider => {
                const item = LAST_PROVIDER_HEALTH[provider] || {};
                const state = ['idle', 'healthy', 'degraded', 'cooldown'].includes(item.state) ? item.state : 'idle';
                const cooldown = Math.max(0, Number(item.cooldown_remaining_sec || 0));
                const stateText = cooldown ? `${stateLabels.cooldown} ${cooldown}s` : stateLabels[state];
                const checks = Math.max(0, Number(item.checks || 0));
                const average = Math.max(0, Number(item.average_elapsed_ms || 0));
                const p95 = Math.max(0, Number(item.p95_elapsed_ms || 0));
                const delay = Math.max(0, Number(item.adaptive_delay_sec || 0));
                const meta = checks ? `${fmt('providerChecks', {count:checks})} · ${fmt('providerAverage', {ms:average})}${p95 ? ` · P95 ${p95}ms` : ''}${delay ? ` · ${delay}s` : ''}` : '';
                const title = item.last_error || `${providerShort(provider)} · ${stateText}`;
                return `<span class="provider-health-chip ${escText(state)}" title="${escText(title)}"><strong>${escText(providerShort(provider))}</strong><span>${escText(stateText)}</span>${meta ? `<small>${escText(meta)}</small>` : ''}</span>`;
              }).join('');
              container.innerHTML = `<span class="provider-health-title">${escText(tx('providerHealth'))}</span>${chips}`;
              container.hidden = false;
            }

            function renderDiagnostics(diagnostics){
              LAST_DIAGNOSTICS = diagnostics && typeof diagnostics === 'object' ? diagnostics : {};
              const value = (id, text) => {
                const node = document.getElementById(id);
                if (node) node.textContent = String(text);
              };
              const throughput = Math.max(0, Number(LAST_DIAGNOSTICS.throughput_per_min || 0));
              const eta = Math.max(0, Number(LAST_DIAGNOSTICS.estimated_remaining_sec || 0));
              const queued = Math.max(0, Number(LAST_DIAGNOSTICS.queue_pending || 0));
              const active = Math.max(0, Number(LAST_DIAGNOSTICS.in_flight || 0));
              const p95 = Math.max(0, Number(LAST_DIAGNOSTICS.slowest_p95_ms || 0));
              const provider = LAST_DIAGNOSTICS.slowest_provider ? providerShort(LAST_DIAGNOSTICS.slowest_provider) : '';
              const manual = Math.max(0, Number(LAST_DIAGNOSTICS.manual_priority_hotels || 0));
              const adaptive = Math.max(0, Number(LAST_DIAGNOSTICS.adaptive_priority_hotels || 0));
              const protection = Math.max(0, Number(LAST_DIAGNOSTICS.access_failures || 0)) + Math.max(0, Number(LAST_DIAGNOSTICS.rate_limited_count || 0));
              const cacheRate = Math.max(0, Number(LAST_DIAGNOSTICS.cache_hit_rate_percent || 0));
              const freshCache = Math.max(0, Number(LAST_DIAGNOSTICS.cache_fresh_entries || 0));
              const savedRequests = Math.max(0, Number(LAST_DIAGNOSTICS.cache_saved_requests || 0));
              value('diagnostics-throughput', `${throughput}/min`);
              value('diagnostics-eta', eta ? hms(eta) : '-');
              value('diagnostics-queue', `${queued} + ${active}`);
              value('diagnostics-latency', p95 ? `${provider ? `${provider} · ` : ''}${p95}ms` : '-');
              value('diagnostics-priority', `${manual} + ${adaptive}`);
              value('diagnostics-protection', protection);
              value('diagnostics-cache', `${cacheRate}% · ${freshCache}`);
              value('diagnostics-saved', savedRequests);
              const summary = document.getElementById('diagnostics-summary');
              if (summary) summary.textContent = `${tx('diagnosticsSummary')} · ${queued + active}`;
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
              if (!cfg) return;
              const dates = `${cfg.start_date || '-'} → ${cfg.end_date || '-'}`;
              const hotelCount = Array.isArray(cfg.hotel_codes)
                ? cfg.hotel_codes.length
                : (Array.isArray(cfg.selected_hotels) ? cfg.selected_hotels.length : 0);
              const engine = cfg.engine === 'playwright' ? 'Playwright' : 'HTTP/API';
              const cadence = `${Number(cfg.loop_interval_seconds || 30)}s`;
              const set = (id, value) => {
                const element = document.getElementById(id);
                if (element) element.textContent = String(value);
              };
              set('snapshot-dates', dates);
              set('snapshot-hotels', hotelCount);
              set('snapshot-engine', engine);
              set('snapshot-cadence', cadence);
            }

            function homeOptionLabel(group, value){
              const maps = {
                zh_cn:{noSmoking:'无烟房',Smoking:'吸烟房',all:'不限制',any:'不限房型',single:'单人房',double:'大床房',twin:'双床房'},
                zh_tw:{noSmoking:'禁菸房',Smoking:'吸菸房',all:'不限制',any:'不限房型',single:'單人房',double:'雙人床房',twin:'雙床房'},
                ja:{noSmoking:'禁煙',Smoking:'喫煙',all:'指定なし',any:'部屋指定なし',single:'シングル',double:'ダブル',twin:'ツイン'},
                ko:{noSmoking:'금연',Smoking:'흡연',all:'제한 없음',any:'객실형 제한 없음',single:'싱글',double:'더블',twin:'트윈'},
                en:{noSmoking:'Non-Smoking',Smoking:'Smoking',all:'Any smoking preference',any:'Any room type',single:'Single',double:'Double',twin:'Twin'}
              };
              const labels = maps[currentLang()] || maps.en;
              if (group === 'smoking') return labels[value] || labels.all;
              return labels[value] || labels.any;
            }

            function homeRelativeTime(timestamp){
              const elapsed = Math.max(0, Date.now() / 1000 - Number(timestamp || 0));
              if (elapsed < 60) return tx('homeJustNow');
              if (elapsed < 3600) return fmt('homeMinutesAgo', {count:Math.floor(elapsed / 60)});
              if (elapsed < 86400) return fmt('homeHoursAgo', {count:Math.floor(elapsed / 3600)});
              return new Date(Number(timestamp || 0) * 1000).toLocaleDateString();
            }

            function homeEventMeta(eventType){
              const map = {
                'availability.available':['eventAvailable','available','✓'],
                'availability.unavailable':['eventUnavailable','unavailable','×'],
                'availability.count_changed':['eventCountChanged','changed','↕'],
                'availability.reminder':['eventReminder','reminder','↻'],
                'search.hotel_error':['eventSearchError','warning','!'],
                'search.started':['eventStarted','started','▶'],
                'search.stopped':['eventStopped','stopped','■']
              };
              const item = map[eventType] || ['eventGeneric','generic','•'];
              return {label:tx(item[0]), cls:item[1], icon:item[2]};
            }

            function renderHomeActivity(events){
              const container = document.getElementById('home-activity-list');
              if (!container) return;
              const items = Array.isArray(events) ? events.slice(0, 5) : [];
              if (!items.length) {
                container.innerHTML = `<div class="home-empty-state">${escText(tx('homeActivityEmpty'))}</div>`;
                return;
              }
              container.innerHTML = items.map(event => {
                const meta = homeEventMeta(event.event_type);
                const code = String(event.payload?.code || '');
                const result = LAST_RESULTS.find(item => String(item.code || '') === code);
                const hotel = result?.name_primary || result?.name || result?.name_en || code || meta.label;
                const count = event.payload?.current_count ?? event.payload?.count;
                const detail = count != null ? `${meta.label} · ${count}` : meta.label;
                return `<button class="home-activity-item ${meta.cls}" type="button" data-home-event-code="${escText(code)}">
                  <i>${meta.icon}</i><span><strong>${escText(hotel)}</strong><small>${escText(detail)}</small></span><time>${escText(homeRelativeTime(event.created_at))}</time>
                </button>`;
              }).join('');
              container.querySelectorAll('[data-home-event-code]').forEach(button => {
                button.addEventListener('click', () => switchAppView('monitor'));
              });
            }

            function renderHomeTrends(data){
              const list = document.getElementById('home-trend-list');
              if (!list) return;
              const points = Array.isArray(data?.points) ? data.points : [];
              const observations = document.getElementById('home-trend-observations');
              if (observations) observations.textContent = String(points.length || Number(LAST_HOME_PAYLOAD?.diagnostics?.trend_observations || 0));
              const hotels = (Array.isArray(data?.hotels) ? data.hotels : [])
                .filter(item => Number(item.samples || 0) > 0)
                .sort((a,b) => Number(b.availability_rate_percent || 0) - Number(a.availability_rate_percent || 0))
                .slice(0, 3);
              if (!hotels.length) {
                list.innerHTML = `<div class="home-empty-state">${escText(tx('homeTrendEmpty'))}</div>`;
                return;
              }
              list.innerHTML = hotels.map(item => {
                const rate = item.availability_rate_percent;
                const result = LAST_RESULTS.find(resultItem => String(resultItem.code || '') === String(item.code || ''));
                const name = item.name || result?.name_primary || result?.name || result?.name_en || item.code;
                const detail = rate == null ? tx('homeNoPrediction') : fmt('homeAvailabilityRate', {rate, samples:item.samples || 0});
                return `<div class="home-trend-item"><div><strong>${escText(name)}</strong><small>${escText(detail)}</small></div><span>${item.latest_price ? `¥${Number(item.latest_price).toLocaleString()}` : '—'}</span><i><b style="width:${Math.max(4, Number(rate || 0))}%"></b></i></div>`;
              }).join('');
            }

            async function refreshHomeInsights(force=false){
              if (!force && (ACTIVE_APP_VIEW !== 'home' || Date.now() - LAST_HOME_REFRESH < 30000)) return;
              const codes = LAST_RESULTS.map(item => item.code).filter(Boolean).join(',');
              LAST_HOME_REFRESH = Date.now();
              try {
                const [eventResponse, trendResponse] = await Promise.all([
                  fetch('/api/v1/events?limit=5'),
                  fetch(`/api/v1/trends?codes=${encodeURIComponent(codes)}&days=30`)
                ]);
                if (eventResponse.ok) {
                  const payload = await eventResponse.json();
                  renderHomeActivity(payload.events || []);
                }
                if (trendResponse.ok) {
                  const payload = await trendResponse.json();
                  renderHomeTrends(payload.trends || {});
                }
              } catch(error) {
                // The regular heartbeat owns the connection state and retry policy.
              }
            }

            function formatTrafficBytes(value){
              let bytes=Math.max(0,Number(value)||0);
              const units=['B','KB','MB','GB','TB'];
              let unit=0;
              while(bytes>=1024&&unit<units.length-1){bytes/=1024;unit+=1;}
              const digits=unit===0||bytes>=100?0:bytes>=10?1:2;
              return `${bytes.toFixed(digits)} ${units[unit]}`;
            }

            function renderHomeDashboard(payload){
              if (!payload) return;
              LAST_HOME_PAYLOAD = payload;
              if (payload.config) LAST_CONFIG = payload.config;
              const cfg = Object.keys(LAST_CONFIG || {}).length ? LAST_CONFIG : {};
              const progress = payload.progress || {};
              const diagnostics = payload.diagnostics || {};
              const running = !!payload.running;
              const hotels = Array.isArray(cfg.hotel_codes) ? cfg.hotel_codes.length : (Array.isArray(cfg.selected_hotels) ? cfg.selected_hotels.length : 0);
              const available = new Set(LAST_RESULTS.filter(item => item.available === true && !item.requirement_unmet).map(item => item.code)).size;
              const providers = [...new Set((cfg.selected_hotels || []).map(item => item.provider || 'toyoko'))];
              if (!providers.length && hotels) providers.push(...(cfg.enabled_providers || ['toyoko']));
              const waiting = running && progress.phase === 'waiting';
              const remaining = waiting ? Math.max(0, Number(progress.wait_total_sec || 0) - Number(progress.wait_elapsed_sec || 0)) : null;
              const nextValue = waiting ? `${Math.ceil(remaining)}s` : (running ? `${Number(progress.done || 0)}/${Number(progress.total || hotels)}` : '—');
              const statusNote = running ? (waiting ? tx('homeWaitingRound') : tx('homeScanning')) : (hotels ? tx('homeReady') : tx('homeWaitingStart'));
              const set = (id, value) => { const element = document.getElementById(id); if (element) element.textContent = String(value); };

              set('home-live-value', running ? tx('running') : tx('stopped'));
              set('home-next-value', nextValue);
              set('home-metric-status', running ? tx('running') : tx('stopped'));
              set('home-metric-status-note', statusNote);
              set('home-metric-available', available);
              set('home-metric-available-note', fmt('homeSelectedHotels', {count:available}));
              set('home-metric-hotels', hotels);
              set('home-metric-hotels-note', hotels ? fmt('homeProviderCount', {count:providers.length}) : tx('homeNoHotels'));
              set('home-metric-next', nextValue);
              set('home-metric-next-note', statusNote);
              const traffic = payload.traffic || {};
              const trafficDown = formatTrafficBytes(traffic.download_bytes);
              const trafficUp = formatTrafficBytes(traffic.upload_bytes);
              const trafficDownRate = formatTrafficBytes(traffic.download_bps);
              const trafficUpRate = formatTrafficBytes(traffic.upload_bps);
              set('home-metric-traffic-down', `↓ ${trafficDown}`);
              set('home-metric-traffic-note', `↑ ${trafficUp} · ${fmt('homeTrafficAccesses', {count:Number(traffic.requests || 0)})}`);
              const trafficCard = document.getElementById('home-traffic-card');
              if (trafficCard) trafficCard.title = fmt('homeTrafficTooltip', {
                down:trafficDown,
                downRate:trafficDownRate,
                up:trafficUp,
                upRate:trafficUpRate,
                visits:Number(traffic.page_views || 0)
              });
              document.getElementById('home-live-dot')?.classList.toggle('running', running);
              document.querySelector('.home-welcome-card')?.classList.toggle('is-running', running);

              const primary = document.getElementById('home-primary-action');
              if (primary) primary.textContent = running ? tx('homeViewMonitor') : (hotels ? tx('homeContinueSearch') : tx('homeSetupSearch'));
              set('home-secondary-action', tx('homeViewMonitor'));
              set('home-hero-summary', running ? fmt('homeRunningSummary', {count:hotels}) : (hotels ? fmt('homeStoppedSummary', {count:hotels}) : tx('homeEmptySummary')));

              const scope = cfg.search_mode === 'radius'
                ? (cfg.radius_query ? `${cfg.radius_query} · ${Number(cfg.radius_km || 5)} km` : tx('homeNoRegion'))
                : (cfg.area_detail_label || cfg.area_region_label || tx('homeNoRegion'));
              set('home-task-title', scope === tx('homeNoRegion') && !hotels ? tx('homeTaskEmpty') : scope);
              set('home-task-state', running ? tx('homeTaskRunning') : (hotels ? tx('homeTaskReady') : tx('homeTaskStopped')));
              set('home-task-checkin', cfg.start_date || '—');
              set('home-task-checkout', cfg.end_date || '—');
              set('home-task-guests', fmt('homeGuestRoom', {people:Number(cfg.people || 1), rooms:Number(cfg.rooms || 1)}));
              set('home-task-preference', `${homeOptionLabel('smoking', cfg.smoking || 'noSmoking')} · ${homeOptionLabel('room', cfg.room_requirement || cfg.om_requirement || 'any')}`);
              set('home-task-scope', scope);
              const chips = document.getElementById('home-provider-chips');
              if (chips) chips.innerHTML = providers.map(provider => `<span class="source-badge ${escText(provider)}">${escText(providerShort(provider))}</span>`).join('');

              const channelCount = (payload.notification_status || []).filter(item => item.enabled).length;
              const providerStates = Object.entries(payload.provider_health || {}).filter(([key]) => !providers.length || providers.includes(key));
              const providerChecked = providerStates.filter(([,state]) => Number(state.checks || 0) > 0);
              const providerHealthy = providerChecked.filter(([,state]) => !['degraded','cooldown'].includes(state.state)).length;
              const providerText = providerChecked.length ? fmt('homeProviderReady', {healthy:providerHealthy, total:providerChecked.length}) : tx('homeNoProviderChecks');
              const attention = !CONNECTION_ONLINE || providerChecked.some(([,state]) => ['degraded','cooldown'].includes(state.state)) || Number(diagnostics.pending_deliveries || 0) > 0;
              set('home-health-badge', attention ? tx('homeAttention') : tx('homeHealthy'));
              set('home-health-connection', CONNECTION_ONLINE ? tx('homeNormal') : tx('connectionOffline'));
              set('home-health-providers', providerText);
              set('home-health-notifications', fmt('homeEnabledChannels', {count:channelCount}));
              set('home-health-data', fmt('homeHistoryRecords', {count:Number(diagnostics.trend_observations || 0)}));
              set('home-trend-observations', Number(diagnostics.trend_observations || 0));
              const healthBadge = document.getElementById('home-health-badge');
              if (healthBadge) healthBadge.classList.toggle('attention', attention);
              refreshHomeInsights(false);
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
                display_code: h.display_code || '',
                provider: h.provider || 'toyoko',
                brand: h.brand || '',
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
                reservation_url: h.reservation_url || '',
                address: h.address || '',
                access: h.access || '',
                lat: h.lat ?? null,
                lng: h.lng ?? null,
                distance_km: h.distance_km ?? null,
                booking_code: h.booking_code || '',
                provider_hotel_id: h.provider_hotel_id || '',
                search_keyword: h.search_keyword || '',
                prefecture: h.prefecture || '',
                region_id: h.region_id ?? null,
                prefecture_id: h.prefecture_id ?? null,
                priority: !!h.priority
              }));
            }
            function currentSearchMode(){
              return document.querySelector('input[name="hotel_picker_mode"]:checked')?.value || 'area';
            }
            function enabledProviders(){
              return PROVIDER_IDS.filter(provider => document.getElementById(`provider_${provider}`)?.checked);
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
                enabled_providers: enabledProviders(),
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
                adaptive_backoff_enabled: document.getElementById('adaptive_backoff_enabled')?.checked ?? true,
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

            const AUTO_SAVE_PREFERENCE_IDS = [
              'primary_language','engine','smart_parallel_enabled','smart_parallel_workers','adaptive_backoff_enabled',
              'loop_interval','per_hotel_delay','request_jitter','alert_repeat','alert_interval',
              'notify_available','notify_unavailable','notify_availability_count_change','notify_start','notify_stop','notify_search_error',
              'enable_telegram','bot_token','chat_id','enable_bark','bark_key','bark_server','bark_critical_enabled','bark_critical_volume','bark_critical_sound',
              'enable_serverchan','serverchan_sendkey','enable_local','enable_email','smtp_host','smtp_port','smtp_tls','smtp_user','smtp_pass','email_from','email_to'
            ];
            const AUTO_SAVE_PREFERENCE_KEYS = [
              'primary_language','engine','smart_parallel_enabled','smart_parallel_workers','adaptive_backoff_enabled',
              'loop_interval_seconds','per_hotel_delay_seconds','request_jitter_percent','available_alert_repeat','available_alert_repeat_interval_sec',
              'notify_available','notify_unavailable','notify_availability_count_change','notify_start','notify_stop','notify_search_error',
              'enable_telegram','bot_token','chat_id','enable_bark','bark_key','bark_server','bark_critical_enabled','bark_critical_volume','bark_critical_sound',
              'enable_serverchan','serverchan_sendkey','enable_local','enable_email','smtp_host','smtp_port','smtp_tls','smtp_user','smtp_pass','email_from','email_to'
            ];
            function collectPreferencePayload(){
              const payload = collectPayload();
              return Object.fromEntries(AUTO_SAVE_PREFERENCE_KEYS.map(key => [key, payload[key]]));
            }
            function schedulePreferenceSave(delay=700){
              if (PREFERENCE_SAVE_TIMER) clearTimeout(PREFERENCE_SAVE_TIMER);
              PREFERENCE_SAVE_TIMER = setTimeout(savePreferencesNow, Math.max(100, Number(delay) || 700));
            }
            async function savePreferencesNow(){
              PREFERENCE_SAVE_TIMER = null;
              if (PREFERENCE_SAVE_IN_FLIGHT) {
                PREFERENCE_SAVE_QUEUED = true;
                return;
              }
              PREFERENCE_SAVE_IN_FLIGHT = true;
              const startedAt = Date.now();
              const payload = collectPreferencePayload();
              try {
                const response = await fetch('/api/v1/preferences', {
                  method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
                });
                const result = await response.json();
                if (!response.ok || !result.ok) throw new Error(result.message || `HTTP ${response.status}`);
                AUTO_SAVE_PREFERENCE_IDS.forEach(id => {
                  if (Number(EDIT_TS[id] || 0) <= startedAt) delete EDIT_TS[id];
                });
                LAST_CONFIG = {...LAST_CONFIG, ...payload};
                if (!Object.keys(EDIT_TS).length) {
                  BLOCK_REMOTE_OVERWRITE = false;
                  setConfigDirty(false);
                }
              } catch(error) {
                const target = document.getElementById('err');
                if (target) target.textContent = String(error);
              } finally {
                PREFERENCE_SAVE_IN_FLIGHT = false;
                if (PREFERENCE_SAVE_QUEUED) {
                  PREFERENCE_SAVE_QUEUED = false;
                  schedulePreferenceSave(150);
                }
              }
            }

            ['start_date','end_date','people','rooms','smoking','room_requirement','membership_status','primary_language','engine',
             'smart_parallel_enabled','smart_parallel_workers','adaptive_backoff_enabled',
             'enable_telegram','bot_token','chat_id','enable_bark','bark_key','bark_server','bark_critical_enabled','bark_critical_volume','bark_critical_sound','enable_serverchan','serverchan_sendkey',
             'enable_local','enable_email','smtp_host','smtp_port','smtp_tls','smtp_user','smtp_pass','email_from','email_to',
             'notify_available','notify_unavailable','notify_availability_count_change','notify_start','notify_stop','notify_search_error',
             'alert_repeat','alert_interval','loop_interval','per_hotel_delay','request_jitter','area_region','area_detail','area_filter','radius_query','radius_km','radius_lat','radius_lng'
            ].forEach(id=>{
              const el = document.getElementById(id);
              if(!el) return;
              el.addEventListener('input', ()=>{ markEdited(id); BLOCK_REMOTE_OVERWRITE = true; if (AUTO_SAVE_PREFERENCE_IDS.includes(id)) schedulePreferenceSave(); });
              el.addEventListener('change', ()=>{ markEdited(id); BLOCK_REMOTE_OVERWRITE = true; if (AUTO_SAVE_PREFERENCE_IDS.includes(id)) schedulePreferenceSave(200); });
            });

            ['alert_repeat','alert_interval','loop_interval','per_hotel_delay','request_jitter','smart_parallel_workers','radius_km','bark_critical_volume'].forEach(id=>{
              const el = document.getElementById(id);
              if(!el) return;
              el.addEventListener('input', syncDisplayValues);
              el.addEventListener('change', syncDisplayValues);
            });
            // Initial sync
            initAppShell();
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
            var AREA_MARKERS_BY_CODE = new Map();
            var AREA_SELECTED_ONLY = false;
            var AREA_SORT = 'default';
            function escText(s){
              return String(s == null ? '' : s).replace(/[&<>"']/g, (m) => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
              }[m]));
            }
            function hotelInfoTravelText(mode, minutes){
              const value = Number(minutes);
              const n = Number.isFinite(value) ? value : '-';
              const labels = {
                zh_cn: {walk:`步行 ${n} 分钟 / ${n} min walk`, drive:`驾车 ${n} 分钟 / ${n} min drive`, bus:`巴士 ${n} 分钟 / ${n} min by bus`},
                zh_tw: {walk:`步行 ${n} 分鐘 / ${n} min walk`, drive:`開車 ${n} 分鐘 / ${n} min drive`, bus:`巴士 ${n} 分鐘 / ${n} min by bus`},
                ja: {walk:`徒歩 ${n}分 / ${n} min walk`, drive:`車で ${n}分 / ${n} min drive`, bus:`バスで ${n}分 / ${n} min by bus`},
                ko: {walk:`도보 ${n}분 / ${n} min walk`, drive:`차량 ${n}분 / ${n} min drive`, bus:`버스 ${n}분 / ${n} min by bus`}
              };
              const dictionary = labels[currentLang()] || labels.zh_cn;
              return dictionary[mode] || dictionary.walk;
            }
            function hotelInfoAccessSection(title, items, type){
              if (!Array.isArray(items) || !items.length) return '';
              const rows = items.map(item => {
                let place = '';
                let travelMode = 'walk';
                if (type === 'train') place = [item.line, item.station, item.exit].filter(Boolean).join(' · ');
                if (type === 'car') {
                  place = [item.road, item.ic].filter(Boolean).join(' · ');
                  travelMode = 'drive';
                }
                if (type === 'plane') {
                  place = [item.airport].filter(Boolean).join(' · ');
                  travelMode = item.transportation === 'walk' ? 'walk' : 'bus';
                }
                return `<li><span>${escText(place)}</span><b>${escText(hotelInfoTravelText(travelMode, item.time))}</b></li>`;
              }).join('');
              return `<section class="hotel-info-section"><h4>${escText(title)}</h4><ul>${rows}</ul></section>`;
            }
            function positionHotelInfoPopover(trigger){
              const panel = document.getElementById('hotel-info-popover');
              if (!panel || !trigger || panel.hidden) return;
              const rect = trigger.getBoundingClientRect();
              const gap = 12;
              const margin = 12;
              if (window.innerWidth <= 720) {
                panel.style.left = `${margin}px`;
                panel.style.right = `${margin}px`;
                panel.style.width = 'auto';
              } else {
                panel.style.right = 'auto';
                panel.style.width = '390px';
                let left = rect.right + gap;
                if (left + 390 > window.innerWidth - margin) left = Math.max(margin, rect.left - 390 - gap);
                panel.style.left = `${left}px`;
              }
              const panelHeight = Math.min(panel.offsetHeight || 420, window.innerHeight - margin * 2);
              const top = Math.max(margin, Math.min(rect.top - 8, window.innerHeight - panelHeight - margin));
              panel.style.top = `${top}px`;
            }
            function renderHotelInfoLoading(trigger){
              destroyHotelInfoMap();
              const panel = document.getElementById('hotel-info-popover');
              if (!panel) return;
              panel.innerHTML = `<div class="hotel-info-head"><div><span>${escText(tx('hotelInfo'))}</span><h3>${escText(trigger.textContent || '')}</h3></div></div><div class="hotel-info-loading"><span></span><span></span><span></span><p>${escText(tx('loadingHotelInfo'))}</p></div>`;
              panel.hidden = false;
              positionHotelInfoPopover(trigger);
            }
            function renderHotelInfoPanel(info, trigger){
              const panel = document.getElementById('hotel-info-popover');
              if (!panel) return;
              destroyHotelInfoMap();
              const mapImage = info.map_image_url
                ? `<a class="hotel-info-map-image" href="${escText(info.google_map_url || info.official_url)}" target="_blank" rel="noreferrer noopener"><img src="${escText(info.map_image_url)}${String(info.map_image_url).includes('toyoko-inn.imagewave.pictures') ? '?width=750' : ''}" alt="${escText(info.name || '')}"></a>`
                : (Number.isFinite(Number(info.lat)) && Number.isFinite(Number(info.lng)) ? '<div id="hotel-info-mini-map" class="hotel-info-mini-map"></div>' : '');
              const train = hotelInfoAccessSection(tx('byTrain'), info.train_access, 'train');
              const car = hotelInfoAccessSection(tx('byCar'), info.car_access, 'car');
              const plane = hotelInfoAccessSection(tx('byPlane'), info.plane_access, 'plane');
              panel.innerHTML = `
                <div class="hotel-info-head"><div><span>${escText(tx('officialReference'))}</span><h3>${escText(info.name || trigger.textContent || '')}</h3></div></div>
                ${mapImage}
                <section class="hotel-info-section hotel-info-address"><h4>${escText(tx('addressLabel'))}</h4><p>${escText(info.address || '-')}</p></section>
                <div class="hotel-info-directions-title">${escText(tx('directionsLabel'))}</div>
                ${train}${car}${plane}
                ${info.access_remarks ? `<p class="hotel-info-remarks">${escText(info.access_remarks)}</p>` : ''}
                <div class="hotel-info-links">
                  <a href="${escText(info.official_url)}" target="_blank" rel="noreferrer noopener">${escText(tx('openOfficial'))}</a>
                  ${info.google_map_url ? `<a href="${escText(info.google_map_url)}" target="_blank" rel="noreferrer noopener">${escText(tx('openMap'))}</a>` : ''}
                </div>`;
              panel.hidden = false;
              const image = panel.querySelector('img');
              if (image) image.addEventListener('error', () => image.closest('.hotel-info-map-image')?.remove(), {once:true});
              const miniMap = panel.querySelector('#hotel-info-mini-map');
              if (miniMap && typeof L !== 'undefined') {
                HOTEL_INFO_MAP = L.map(miniMap, {zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false})
                  .setView([Number(info.lat), Number(info.lng)], 15);
                L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19}).addTo(HOTEL_INFO_MAP);
                L.marker([Number(info.lat), Number(info.lng)]).addTo(HOTEL_INFO_MAP);
              }
              requestAnimationFrame(() => positionHotelInfoPopover(trigger));
            }
            function renderHotelInfoError(trigger){
              const panel = document.getElementById('hotel-info-popover');
              if (!panel) return;
              destroyHotelInfoMap();
              panel.innerHTML = `<div class="hotel-info-head"><div><span>${escText(tx('hotelInfo'))}</span><h3>${escText(trigger.textContent || '')}</h3></div></div><div class="hotel-info-error">${escText(tx('hotelInfoUnavailable'))}</div>`;
              panel.hidden = false;
              positionHotelInfoPopover(trigger);
            }
            async function hotelInfoFor(code, language){
              const key = `${code}:${language}`;
              if (HOTEL_INFO_CACHE.has(key)) return HOTEL_INFO_CACHE.get(key);
              if (!HOTEL_INFO_REQUESTS.has(key)) {
                const requestPromise = fetch(`/hotel_info?code=${encodeURIComponent(code)}&language=${encodeURIComponent(language)}`)
                  .then(async response => {
                    const payload = await response.json();
                    if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
                    HOTEL_INFO_CACHE.set(key, payload.info);
                    return payload.info;
                  })
                  .finally(() => HOTEL_INFO_REQUESTS.delete(key));
                HOTEL_INFO_REQUESTS.set(key, requestPromise);
              }
              return HOTEL_INFO_REQUESTS.get(key);
            }
            async function showHotelInfo(trigger){
              const rawCode = String(trigger?.dataset?.hotelCode || '').trim();
              const code = /^\d{1,5}$/.test(rawCode) ? rawCode.padStart(5, '0') : rawCode;
              if (!code || code.length > 160) return;
              ACTIVE_HOTEL_INFO_TRIGGER = trigger;
              const language = currentLang();
              const requestKey = `${code}:${language}`;
              renderHotelInfoLoading(trigger);
              try {
                const info = await hotelInfoFor(code, language);
                if (ACTIVE_HOTEL_INFO_TRIGGER !== trigger || `${code}:${currentLang()}` !== requestKey) return;
                renderHotelInfoPanel(info, trigger);
              } catch(e) {
                if (ACTIVE_HOTEL_INFO_TRIGGER === trigger) renderHotelInfoError(trigger);
              }
            }
            function scheduleHotelInfoShow(trigger){
              clearTimeout(HOTEL_INFO_HIDE_TIMER);
              clearTimeout(HOTEL_INFO_SHOW_TIMER);
              if (ACTIVE_HOTEL_INFO_TRIGGER === trigger && !document.getElementById('hotel-info-popover')?.hidden) return;
              HOTEL_INFO_SHOW_TIMER = setTimeout(() => showHotelInfo(trigger), 350);
            }
            function hideHotelInfoNow(){
              clearTimeout(HOTEL_INFO_SHOW_TIMER);
              destroyHotelInfoMap();
              const panel = document.getElementById('hotel-info-popover');
              if (panel) panel.hidden = true;
              ACTIVE_HOTEL_INFO_TRIGGER = null;
            }
            function destroyHotelInfoMap(){
              if (!HOTEL_INFO_MAP) return;
              try { HOTEL_INFO_MAP.remove(); } catch(e) {}
              HOTEL_INFO_MAP = null;
            }
            function scheduleHotelInfoHide(){
              clearTimeout(HOTEL_INFO_SHOW_TIMER);
              clearTimeout(HOTEL_INFO_HIDE_TIMER);
              HOTEL_INFO_HIDE_TIMER = setTimeout(hideHotelInfoNow, 180);
            }
            function initHotelInfoPreview(){
              const panel = document.getElementById('hotel-info-popover');
              if (!panel) return;
              document.addEventListener('pointerover', event => {
                const trigger = event.target.closest?.('.hotel-info-trigger');
                if (!trigger || trigger.contains(event.relatedTarget)) return;
                scheduleHotelInfoShow(trigger);
              });
              document.addEventListener('pointerout', event => {
                const trigger = event.target.closest?.('.hotel-info-trigger');
                if (!trigger || trigger.contains(event.relatedTarget) || panel.contains(event.relatedTarget)) return;
                scheduleHotelInfoHide();
              });
              document.addEventListener('focusin', event => {
                const trigger = event.target.closest?.('.hotel-info-trigger');
                if (trigger) scheduleHotelInfoShow(trigger);
              });
              document.addEventListener('focusout', event => {
                const trigger = event.target.closest?.('.hotel-info-trigger');
                if (trigger && !panel.contains(event.relatedTarget)) scheduleHotelInfoHide();
              });
              panel.addEventListener('pointerenter', () => clearTimeout(HOTEL_INFO_HIDE_TIMER));
              panel.addEventListener('pointerleave', scheduleHotelInfoHide);
              panel.addEventListener('focusin', () => clearTimeout(HOTEL_INFO_HIDE_TIMER));
              panel.addEventListener('focusout', event => {
                if (!panel.contains(event.relatedTarget)) scheduleHotelInfoHide();
              });
              document.addEventListener('keydown', event => {
                if (event.key === 'Escape') hideHotelInfoNow();
              });
              window.addEventListener('resize', () => {
                if (ACTIVE_HOTEL_INFO_TRIGGER) positionHotelInfoPopover(ACTIVE_HOTEL_INFO_TRIGGER);
              });
            }
            function setAreaStatus(text, isError=false){
              const el = document.getElementById('area_status');
              if (!el) return;
              el.textContent = text;
              el.style.color = isError ? '#a33a3a' : '#777';
            }
            function setAreaLoading(buttonId, loading){
              const button = document.getElementById(buttonId);
              if (!button) return;
              if (loading) {
                button.dataset.idleText = button.textContent;
                button.textContent = tx('loadingHotels');
              } else if (button.dataset.idleText) {
                button.textContent = button.dataset.idleText;
                delete button.dataset.idleText;
              }
              button.disabled = !!loading;
              button.setAttribute('aria-busy', loading ? 'true' : 'false');
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
            function catalogDateText(value){
              if (!value) return tx('catalogNeverChecked');
              const date = new Date(value);
              if (Number.isNaN(date.getTime())) return tx('catalogNeverChecked');
              const locale = {zh_cn:'zh-CN', zh_tw:'zh-TW', ja:'ja-JP', ko:'ko-KR', en:'en-US'}[currentLang()] || 'en-US';
              const time = date.toLocaleString(locale, {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'});
              return fmt('catalogCheckedAt', {time});
            }
            function catalogHotelLink(hotel){
              const code = String(hotel?.code || '');
              const name = bilingualText(hotel?.name_primary || hotel?.name || '', hotel?.name_en || hotel?.name || '');
              const text = `${code}${name ? ` ${name}` : ''}`;
              return hotel?.url
                ? `<a href="${escText(hotel.url)}" target="_blank" rel="noreferrer noopener">${escText(text)}</a>`
                : escText(text);
            }
            function renderHotelCatalog(status){
              if (status) LAST_CATALOG_STATUS = status;
              const data = LAST_CATALOG_STATUS;
              const panel = document.getElementById('hotel_catalog_panel');
              if (!panel || !data) return;
              const state = String(data.state || 'idle');
              panel.className = `catalog-status ${state}${data.cache_fresh === false ? ' stale' : ''}`;
              const titleByState = {
                checking: 'catalogChecking', failed: 'catalogFailed', updated: 'catalogUpdated',
                fresh: 'catalogFresh', idle: 'catalogTitle'
              };
              const title = document.getElementById('hotel_catalog_title');
              if (title) title.textContent = tx(titleByState[state] || 'catalogTitle');
              const cacheText = tx(data.cache_fresh ? 'catalogCacheFresh' : 'catalogCacheStale');
              let metaText = fmt('catalogMeta', {
                open: Number(data.open_japan_count || 0),
                coords: Number(data.coordinate_count || 0),
                cache: cacheText,
                checked: catalogDateText(data.checked_at)
              });
              const unresolved = Number(data.unresolved_coordinate_count || 0);
              if (unresolved > 0) metaText += ` · ${fmt('catalogUnresolved', {count: unresolved})}`;
              if (state === 'failed' && data.last_error) metaText += ` · ${String(data.last_error).slice(0, 180)}`;
              const meta = document.getElementById('hotel_catalog_meta');
              if (meta) meta.textContent = metaText;

              const upcoming = Array.isArray(data.upcoming_hotels) ? data.upcoming_hotels : [];
              const upcomingEl = document.getElementById('hotel_catalog_upcoming');
              if (upcomingEl) {
                const names = upcoming.slice(0, 4).map(h => `${h.code} ${h.name || ''}`.trim()).join(' · ');
                upcomingEl.textContent = upcoming.length ? fmt('catalogUpcoming', {count: upcoming.length, hotels: names}) : '';
                upcomingEl.hidden = !upcoming.length;
              }

              const newHotels = Array.isArray(data.new_hotels) ? data.new_hotels : [];
              const newEl = document.getElementById('hotel_catalog_new');
              if (newEl) {
                newEl.innerHTML = newHotels.length
                  ? `<strong>${escText(fmt('catalogNewTitle', {count: newHotels.length}))}</strong><div>${newHotels.map(catalogHotelLink).join(' · ')}</div>`
                  : '';
                newEl.hidden = !newHotels.length;
              }
              const ack = document.getElementById('btn_catalog_ack');
              if (ack) ack.hidden = !newHotels.length;
              const refresh = document.getElementById('btn_catalog_refresh');
              if (refresh) refresh.disabled = state === 'checking';
            }
            function renderProviderCatalog(status){
              LAST_PROVIDER_CATALOG_STATUS = status;
              const meta = document.getElementById('provider_catalog_meta');
              const newEl = document.getElementById('provider_catalog_new');
              if (!meta || !status) return;
              const records = status.providers || {};
              const parts = ['routeinn','dormy','mystays','daiwa'].map(provider => {
                const row = records[provider] || {};
                return `${providerShort(provider)} ${Number(row.hotel_count || 0)}`;
              });
              const prefix = tx('providerCatalogDb');
              meta.textContent = `${prefix}: ${parts.join(' · ')}${status.checking ? ` · ${tx('catalogUpdating')}` : ''}`;
              const changes = [];
              Object.entries(records).forEach(([provider, row]) => {
                (Array.isArray(row.new_hotels) ? row.new_hotels : []).forEach(hotel => {
                  changes.push(`${providerShort(provider)} · ${hotel.code} ${hotel.name || ''}`.trim());
                });
              });
              if (newEl) {
                newEl.innerHTML = changes.length
                  ? `<strong>${escText(fmt('providerCatalogNew', {count: changes.length}))}</strong><div>${changes.map(escText).join(' · ')}</div>`
                  : '';
                newEl.hidden = !changes.length;
              }
            }
            async function refreshHotelCatalog(){
              setButtonBusy('btn_catalog_refresh', true);
              try {
                const [response, providerResponse] = await Promise.all([
                  fetch('/hotel_catalog_refresh', {method:'POST'}),
                  fetch('/provider_catalog_refresh', {method:'POST'})
                ]);
                const payload = await response.json();
                const providerPayload = await providerResponse.json();
                if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
                if (!providerResponse.ok || !providerPayload.ok) throw new Error(providerPayload.error || `HTTP ${providerResponse.status}`);
                renderHotelCatalog(payload.catalog);
                const msg = document.getElementById('msg');
                if (msg) msg.textContent = tx('catalogRefreshQueued');
              } catch (error) {
                const err = document.getElementById('err');
                if (err) err.textContent = `${tx('catalogFailed')}: ${error}`;
              } finally {
                setButtonBusy('btn_catalog_refresh', false);
              }
            }
            async function acknowledgeNewHotels(){
              setButtonBusy('btn_catalog_ack', true);
              try {
                const response = await fetch('/hotel_catalog_acknowledge', {method:'POST'});
                const payload = await response.json();
                if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
                renderHotelCatalog(payload.catalog);
              } finally {
                setButtonBusy('btn_catalog_ack', false);
              }
            }
            function clearSelectedHotelMap(){
              if (AREA_SELECTED_MAP && Array.isArray(AREA_SELECTED_MARKERS)) {
                AREA_SELECTED_MARKERS.forEach(marker => {
                  try { AREA_SELECTED_MAP.removeLayer(marker); } catch(e) {}
                });
              }
              AREA_SELECTED_MARKERS = [];
              AREA_MARKERS_BY_CODE.clear();
            }
            function updateAreaSelectionSummary(){
              const selected = selectedAreaCodes().length;
              const total = Array.isArray(AREA_HOTELS) ? AREA_HOTELS.length : 0;
              const summary = document.getElementById('area_selection_summary');
              if (summary) summary.textContent = fmt('selectedSummary', {selected, total});
              const dockSummary = document.getElementById('dock-summary');
              if (dockSummary) {
                dockSummary.textContent = selected > 0
                  ? fmt('dockSelected', {count: selected})
                  : tx('dockNoHotels');
              }
              const sidebarCount = document.getElementById('sidebar-hotel-count');
              if (sidebarCount) sidebarCount.textContent = fmt('sidebarHotelCount', {count:selected});
            }
            function syncProviderAllButton(){
              const button = document.getElementById('btn_provider_all');
              if (!button) return;
              const allEnabled = enabledProviders().length === PROVIDER_IDS.length;
              button.classList.toggle('active', allEnabled);
              button.setAttribute('aria-pressed', allEnabled ? 'true' : 'false');
            }
            function focusAreaMarker(code, scrollRow=false){
              const marker = AREA_MARKERS_BY_CODE.get(String(code || ''));
              if (marker) {
                try {
                  AREA_SELECTED_MAP?.panTo(marker.getLatLng(), {animate:true, duration:.35});
                  marker.openPopup();
                } catch(e) {}
              }
              if (!scrollRow) return;
              const row = document.querySelector(`.hotel-item[data-hotel-code="${CSS.escape(String(code || ''))}"]`);
              if (!row) return;
              row.scrollIntoView({behavior:'smooth', block:'nearest'});
              row.classList.add('map-highlight');
              setTimeout(() => row.classList.remove('map-highlight'), 1400);
            }
            function renderSelectedHotelMap(){
              const panel = document.getElementById('area_map_panel');
              const status = document.getElementById('area_map_status');
              const legend = document.getElementById('area_map_legend');
              const mapEl = document.getElementById('area_selected_map');
              if (!panel || !status || !mapEl) return;
              const selected = selectedAreaHotels();
              const withCoords = selected.map(h => ({hotel: h, coord: validMapCoord(h)})).filter(x => x.coord);
              if (legend) {
                const providers = [...new Set(withCoords.map(({hotel}) => PROVIDER_IDS.includes(hotel.provider) ? hotel.provider : 'toyoko'))];
                legend.innerHTML = providers.map(provider =>
                  `<span><i class="map-legend-dot ${provider}"></i>${escText(providerShort(provider))}</span>`
                ).join('');
              }
              if (!AREA_HOTELS.length || selected.length === 0){
                panel.hidden = true;
                clearSelectedHotelMap();
                const mapButton = document.querySelector('[data-hotel-workspace-view="map"]');
                if (mapButton) mapButton.disabled = true;
                setHotelWorkspaceView('list');
                return;
              }
              panel.hidden = false;
              const mapButton = document.querySelector('[data-hotel-workspace-view="map"]');
              if (mapButton) mapButton.disabled = false;
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
                  <div class="map-popup-title">${escText(hotel.display_code || hotel.code)} · ${escText(name)}</div>
                  <div class="map-popup-links">
                    <a href="${escText(hotel.url || '#')}" target="_blank" rel="noreferrer noopener">${escText(tx('official'))}</a>
                    ${hotel.map_url ? `<a href="${escText(hotel.map_url)}" target="_blank" rel="noreferrer noopener">${escText(tx('openMap'))}</a>` : ''}
                  </div>
                `;
                const provider = PROVIDER_IDS.includes(hotel.provider) ? hotel.provider : 'toyoko';
                const icon = L.divIcon({
                  className: 'provider-map-marker-wrap',
                  html: `<span class="provider-map-marker ${provider}"><i></i></span>`,
                  iconSize: [26, 34],
                  iconAnchor: [13, 32],
                  popupAnchor: [0, -30]
                });
                const marker = L.marker([coord.lat, coord.lng], {icon}).addTo(AREA_SELECTED_MAP).bindPopup(popup);
                const code = String(hotel.code || '');
                AREA_MARKERS_BY_CODE.set(code, marker);
                marker.on('click', () => focusAreaMarker(code, true));
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
            function setHotelWorkspaceView(view){
              const next = view === 'map' ? 'map' : 'list';
              const workspace = document.getElementById('hotel_workspace');
              if (workspace) workspace.dataset.mobileView = next;
              document.querySelectorAll('[data-hotel-workspace-view]').forEach(button => {
                const active = button.dataset.hotelWorkspaceView === next;
                button.classList.toggle('active', active);
                button.setAttribute('aria-pressed', active ? 'true' : 'false');
              });
              if (next === 'map') setTimeout(() => {
                try { AREA_SELECTED_MAP?.invalidateSize(); } catch(e) {}
              }, 80);
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
              const normalizedName = (hotel) => bilingualText(
                hotel.name_primary || hotel.name_zh || hotel.name || '',
                hotel.name_en || hotel.name || ''
              ).toLocaleLowerCase();
              const hotels = AREA_HOTELS.filter(h => {
                if (AREA_SELECTED_ONLY && !AREA_SELECTED_CODES?.has(String(h.code || ''))) return false;
                if (!filter) return true;
                return String(h.code || '').toLowerCase().includes(filter)
                  || String(h.display_code || '').toLowerCase().includes(filter)
                  || String(h.name || '').toLowerCase().includes(filter)
                  || String(h.name_en || '').toLowerCase().includes(filter)
                  || String(h.name_primary || '').toLowerCase().includes(filter)
                  || String(h.name_zh || '').toLowerCase().includes(filter)
                  || String(h.name_zh_cn || '').toLowerCase().includes(filter)
                  || String(h.name_zh_tw || '').toLowerCase().includes(filter)
                  || String(h.name_ja || '').toLowerCase().includes(filter)
                  || String(h.name_ko || '').toLowerCase().includes(filter);
              });
              if (AREA_SORT !== 'default') {
                hotels.sort((a, b) => {
                  if (AREA_SORT === 'distance') {
                    const ad = Number(a.distance_km);
                    const bd = Number(b.distance_km);
                    const aValue = Number.isFinite(ad) ? ad : Number.POSITIVE_INFINITY;
                    const bValue = Number.isFinite(bd) ? bd : Number.POSITIVE_INFINITY;
                    return aValue - bValue || normalizedName(a).localeCompare(normalizedName(b));
                  }
                  if (AREA_SORT === 'name') return normalizedName(a).localeCompare(normalizedName(b));
                  return String(a.display_code || a.code || '').localeCompare(String(b.display_code || b.code || ''), undefined, {numeric:true});
                });
              }
              const visibleSummary = document.getElementById('area_visible_summary');
              if (visibleSummary) visibleSummary.textContent = fmt('visibleHotels', {shown:hotels.length, total:AREA_HOTELS.length});
              if (!hotels.length){
                wrap.innerHTML = `<div class="hotel-picker-empty">${escText(tx('noMatchingHotels'))}</div>`;
                updateAreaSelectionSummary();
                renderSelectedHotelMap();
                return;
              }
              wrap.innerHTML = hotels.map(h => `
                <div class="hotel-item ${AREA_SELECTED_CODES?.has(String(h.code || '')) ? 'selected' : ''}" data-hotel-code="${escText(h.code)}">
                  <label>
	                    <input class="area-hotel-check" type="checkbox" value="${escText(h.code)}" ${AREA_SELECTED_CODES?.has(String(h.code || '')) ? 'checked' : ''}>
                    <span class="hotel-code">${escText(h.display_code || h.code)}</span>
                    <span class="hotel-name hotel-actions">
                      <span>
                        <a class="hotel-info-trigger" data-hotel-code="${escText(h.code)}" href="${escText(h.url || '#')}" target="_blank" rel="noreferrer noopener">${escText(bilingualText(h.name_primary || h.name_zh || h.name || '', h.name_en || h.name || '(Hotel name not found)'))}</a>
                        <span class="source-badge ${escText(h.provider || 'toyoko')}">${escText(providerShort(h.provider || 'toyoko'))}</span>
                        ${h.distance_km != null ? `<span class="distance-badge">${escText(h.distance_km)} km</span>` : ''}
                      </span>
                      <a class="hotel-map" href="${escText(h.map_url || '#')}" target="_blank" rel="noreferrer noopener">${escText(tx('openMap'))}</a>
                    </span>
	                  </label>
	                  <button type="button" class="hotel-priority-button ${h.priority ? 'active' : ''}" data-hotel-priority="${escText(h.code)}" aria-pressed="${h.priority ? 'true' : 'false'}" title="${escText(tx(h.priority ? 'removePriority' : 'priorityHotel'))}">${h.priority ? '★' : '☆'}</button>
	                </div>
	              `).join('');
              wrap.querySelectorAll('.area-hotel-check').forEach(el => {
                el.addEventListener('change', () => {
                  if (!(AREA_SELECTED_CODES instanceof Set)) AREA_SELECTED_CODES = new Set();
                  if (el.checked) AREA_SELECTED_CODES.add(String(el.value));
                  else AREA_SELECTED_CODES.delete(String(el.value));
                  el.closest('.hotel-item')?.classList.toggle('selected', el.checked);
                  markEdited('hotel_codes');
                  BLOCK_REMOTE_OVERWRITE = true;
                  updateAreaSelectionSummary();
                  renderSelectedHotelMap();
                  if (AREA_SELECTED_ONLY) renderAreaHotels();
                });
              });
              wrap.querySelectorAll('.hotel-item').forEach(row => {
                const code = String(row.dataset.hotelCode || '');
                const showMarker = () => focusAreaMarker(code);
                row.addEventListener('mouseenter', showMarker);
                row.addEventListener('focusin', showMarker);
                row.addEventListener('click', (event) => {
                  if (event.target.closest('a,button,input,label')) return;
                  focusAreaMarker(code);
                });
              });
              wrap.querySelectorAll('[data-hotel-priority]').forEach(button => {
                button.addEventListener('click', event => {
                  event.preventDefault();
                  event.stopPropagation();
                  const code = String(button.dataset.hotelPriority || '');
                  const hotel = AREA_HOTELS.find(item => String(item.code || '') === code);
                  if (!hotel) return;
                  hotel.priority = !hotel.priority;
                  markEdited('selected_hotels');
                  BLOCK_REMOTE_OVERWRITE = true;
                  renderAreaHotels();
                });
              });
              updateAreaSelectionSummary();
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
              const providers = enabledProviders();
              if (!providers.length){
                setAreaStatus(tx('providerRequired'), true);
                return;
              }
              setAreaStatus(tx('loadingHotels'));
              setAreaLoading('btn_area_load', true);
              try{
                const r = await fetch('/area_hotels', {
                  method:'POST',
                  headers:{'Content-Type':'application/json'},
                  body: JSON.stringify({
                    region_id: regionId,
                    detail_id: detailSel?.value || '',
                    primary_language: document.getElementById('primary_language')?.value || 'zh_cn',
                    providers
                  })
                });
                const j = await r.json();
                if (!j.ok) throw new Error(j.error || 'load failed');
                AREA_HOTELS = Array.isArray(j.hotels) ? j.hotels : [];
                AREA_SELECTED_CODES = new Set(AREA_HOTELS.map(h => String(h.code || '')));
                markEdited('hotel_codes');
                BLOCK_REMOTE_OVERWRITE = true;
                renderAreaHotels();
                const n = AREA_HOTELS.length;
                const counts = j.provider_counts || {};
                const parts = [];
                PROVIDER_IDS.forEach(provider => {
                  if (counts[provider] != null) parts.push(`${providerShort(provider)} ${counts[provider]}`);
                });
                const warning = Object.keys(j.provider_errors || {}).length ? ` · ${tx('partialProviderFailure')}` : '';
                setAreaStatus(`${fmt('loadedHotels', {count: n})}${parts.length ? ` · ${parts.join(' / ')}` : ''}${warning}`);
	              }catch(e){
	                AREA_HOTELS = [];
	                AREA_SELECTED_CODES = null;
                renderAreaHotels();
                setAreaStatus(tx('hotelLoadingFailed') + e, true);
              } finally {
                setAreaLoading('btn_area_load', false);
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
              setAreaLoading('btn_radius_load', true);
              try{
                const r = await fetch('/radius_hotels', {
                  method:'POST',
                  headers:{'Content-Type':'application/json'},
                  body: JSON.stringify({
                    query,
                    radius_km: radiusKm,
                    primary_language: document.getElementById('primary_language')?.value || 'zh_cn',
                    providers: enabledProviders()
                  })
                });
                const j = await r.json();
                if (!j.ok) throw new Error(j.error || 'radius load failed');
                AREA_HOTELS = Array.isArray(j.hotels) ? j.hotels : [];
                AREA_SELECTED_CODES = new Set(AREA_HOTELS.map(h => String(h.code || '')));
                markEdited('hotel_codes');
                BLOCK_REMOTE_OVERWRITE = true;
                if (j.center){
                  document.getElementById('radius_lat').value = j.center.lat ?? '';
                  document.getElementById('radius_lng').value = j.center.lng ?? '';
                }
                renderAreaHotels();
                const n = AREA_HOTELS.length;
                const centerText = j.center ? `${j.center.lat}, ${j.center.lng}` : query;
                const counts = j.provider_counts || {};
                const parts = [];
                PROVIDER_IDS.forEach(provider => {
                  if (counts[provider] != null) parts.push(`${providerShort(provider)} ${counts[provider]}`);
                });
                setAreaStatus(`${fmt('loadedHotelsCenter', {count: n, center: centerText})}${parts.length ? ` · ${parts.join(' / ')}` : ''}`);
	              }catch(e){
	                AREA_HOTELS = [];
	                AREA_SELECTED_CODES = null;
                renderAreaHotels();
                setAreaStatus(tx('radiusSearchFailed') + e, true);
              } finally {
                setAreaLoading('btn_radius_load', false);
              }
            }
            function setAreaHotelChecks(checked){
              AREA_SELECTED_CODES = checked ? new Set(AREA_HOTELS.map(h => String(h.code || ''))) : new Set();
              document.querySelectorAll('.area-hotel-check').forEach(el => { el.checked = checked; });
              markEdited('hotel_codes');
              BLOCK_REMOTE_OVERWRITE = true;
              renderAreaHotels();
            }
            initAreaPicker();
            setPickerMode(currentSearchMode());

            function historyHotelList(record){
              const hotels = Array.isArray(record.selected_hotels) ? record.selected_hotels : [];
              if (hotels.length) return hotels.map(h => ({
                code: String(h.code || ''),
                display_code: h.display_code || '',
                provider: h.provider || (String(h.code || '').includes(':') ? String(h.code).split(':', 1)[0] : 'toyoko'),
                brand: h.brand || '',
                name: h.name || h.name_en || h.name_zh || '',
                name_primary: h.name_primary || '',
                name_zh: h.name_zh || '',
                name_zh_cn: h.name_zh_cn || h.name_zh || '',
                name_zh_tw: h.name_zh_tw || '',
                name_ja: h.name_ja || '',
                name_ko: h.name_ko || '',
                name_en: h.name_en || h.name || '',
                url: h.url || (String(h.code || '').includes(':') ? '' : `https://www.toyoko-inn.com/eng/search/detail/${String(h.code || '').padStart(5,'0')}/`),
                map_url: h.map_url || '',
                reservation_url: h.reservation_url || '',
                address: h.address || '',
                access: h.access || '',
                lat: h.lat ?? null,
                lng: h.lng ?? null,
                distance_km: h.distance_km ?? null,
                booking_code: h.booking_code || '',
                provider_hotel_id: h.provider_hotel_id || '',
                search_keyword: h.search_keyword || '',
                prefecture: h.prefecture || '',
                region_id: h.region_id ?? null,
                prefecture_id: h.prefecture_id ?? null,
                priority: !!h.priority
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
                const region = historyAreaFallback('region', r.area_region);
                const detail = historyAreaFallback('detail', r.area_detail);
                const scope = r.search_mode === 'radius'
                  ? `${escText(r.radius_query || '')} · ${escText(r.radius_km || 5)} km`
                  : `${escText(region)} · ${escText(detail)}`;
                const title = `${escText(r.start_date || '')} → ${escText(r.end_date || '')} · ${escText(fmt('historyHotelCount', {count}))}`;
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
              setPanelOpen('#search_panel, details.settings-panel', false);
            }
            function expandSearchAreaPicker(){
              setPanelOpen('#search_panel', true);
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
              const historyProviders = Array.isArray(record.enabled_providers) ? record.enabled_providers : DEFAULT_PROVIDER_IDS;
              PROVIDER_IDS.forEach(provider => {
                const checkbox = document.getElementById(`provider_${provider}`);
                if (checkbox) checkbox.checked = historyProviders.includes(provider);
              });
              setValue('engine', record.engine || 'http');
              const parallelEl = document.getElementById('smart_parallel_enabled');
              if (parallelEl) parallelEl.checked = !!record.smart_parallel_enabled;
              const backoffEl = document.getElementById('adaptive_backoff_enabled');
              if (backoffEl) backoffEl.checked = record.adaptive_backoff_enabled !== false;
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
              markEdited('search_history');
              BLOCK_REMOTE_OVERWRITE = true;
            }

            function restoreAreaFromConfig(cfg){
              if (!cfg || BLOCK_REMOTE_OVERWRITE) return;
              const configuredProviders = Array.isArray(cfg.enabled_providers) ? cfg.enabled_providers : DEFAULT_PROVIDER_IDS;
              PROVIDER_IDS.forEach(provider => {
                const checkbox = document.getElementById(`provider_${provider}`);
                if (checkbox && !recentlyEdited(`provider_${provider}`)) checkbox.checked = configuredProviders.includes(provider);
              });
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

            function setButtonBusy(id, busy){
              const button = document.getElementById(id);
              if (!button) return;
              if (busy) button.disabled = true;
              else if (id === 'btn_stop') button.disabled = !LAST_RUNNING;
              else if (id === 'btn_scan_once') button.disabled = LAST_RUNNING;
              else button.disabled = false;
              button.setAttribute('aria-busy', busy ? 'true' : 'false');
            }
            function preflightSearch(){
              const payload = collectPayload();
              const error = document.getElementById('err');
              const message = document.getElementById('msg');
              if (!payload.start_date || !payload.end_date || payload.end_date <= payload.start_date){
                switchAppView('search', {instant:true});
                if (error) error.textContent = tx('invalidDates');
                if (message) message.textContent = '';
                setPanelOpen('#search_panel', true);
                document.getElementById('start_date')?.focus();
                return null;
              }
              if (!validateBarkKeyInput()) return null;
              if (!Array.isArray(payload.hotel_codes) || payload.hotel_codes.length === 0){
                switchAppView('search', {instant:true});
                if (error) error.textContent = tx('selectHotelsFirst');
                if (message) message.textContent = '';
                expandSearchAreaPicker();
                document.getElementById('area_picker_panel')?.scrollIntoView({behavior:'smooth', block:'center'});
                return null;
              }
              return payload;
            }
            async function callStart(runOnce=false){
              const payload = preflightSearch();
              if (!payload) return;
              payload.run_once = !!runOnce;
              const buttonId = runOnce ? 'btn_scan_once' : 'btn_start';
              setButtonBusy(buttonId, true);
              try {
                const r = await fetch('/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
                const j = await r.json();
                if (j.ok) {
                  document.getElementById('msg').textContent = runOnce
                    ? tx('scanningOnce')
                    : (j.restarted ? tx('restartedMessage') : tx('startedMessage'));
                  document.getElementById('err').textContent = '';
	                  setRunning(true);
	                  Object.keys(EDIT_TS).forEach(key => delete EDIT_TS[key]);
	                  BLOCK_REMOTE_OVERWRITE = false;
	                  setConfigDirty(false);
	                  renderSummary(payload);
	                  RESULT_CHANGED_CODES.clear();
	                  RESULT_CHANGE_CLASSES.clear();
	                  const changeNote = document.getElementById('result-change-note');
	                  if (changeNote) changeNote.hidden = true;
	                  collapseSearchPanels();
	                  refreshSearchHistory();
                } else {
                  document.getElementById('err').textContent = j.error || tx('failedToStart');
                  document.getElementById('msg').textContent = '';
                }
                refreshStatus();
              } catch(e) {
                document.getElementById('err').textContent = e;
                document.getElementById('msg').textContent = '';
              } finally {
                setButtonBusy(buttonId, false);
              }
            }
            async function callStop(){
              setButtonBusy('btn_stop', true);
              try {
                const r = await fetch('/stop', {method:'POST'});
                const j = await r.json();
                if (j.ok) {
                  document.getElementById('msg').textContent = tx('stoppedMessage');
                  document.getElementById('err').textContent = '';
	                  setRunning(false);
	                  expandSearchAreaPicker();
                } else {
                  document.getElementById('err').textContent = tx('failedToStop');
                  document.getElementById('msg').textContent = '';
                }
              } catch(e) {
                document.getElementById('err').textContent = e;
                document.getElementById('msg').textContent = '';
              } finally {
                setButtonBusy('btn_stop', false);
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

            function versionLabel(value){
              const text = String(value || '').trim();
              if (!text) return '-';
              return /^v/i.test(text) ? text : `v${text}`;
            }
            function renderUpdateDialog(update){
              if (update) LAST_UPDATE_STATUS = update;
              const data = update || LAST_UPDATE_STATUS || {};
              const state = data.state || 'idle';
              const current = versionLabel(data.current_version || document.body.dataset.appVersion);
              const latest = versionLabel(data.latest_version);
              const desktopUpdate = data.install_method === 'download';
              setNodeText('#update-current-version', current);
              setNodeText('#update-latest-version', latest);

              const row = document.getElementById('update-state-row');
              const title = document.getElementById('update-state-title');
              const message = document.getElementById('update-state-message');
              const upgradeButton = document.getElementById('btn_upgrade');
              const checkButton = document.getElementById('btn_update_check');
              const openButton = document.getElementById('update-open-button');
              if (row) row.dataset.state = state;
              openButton?.classList.toggle('has-update', state === 'update_available');

              let titleText = tx('updateUnknown');
              let messageText = '';
              let upgradeText = tx('updateButton');
              let canUpgrade = false;
              if (state === 'checking') {
                titleText = tx('checkingUpdate');
                messageText = desktopUpdate ? '正在检查 GitHub Releases / Checking GitHub Releases' : tx('checkingUpdateMessage');
                upgradeText = tx('updateButton');
              } else if (state === 'up_to_date') {
                titleText = tx('upToDate');
                messageText = tx('upToDateMessage');
                upgradeText = tx('upToDate');
              } else if (state === 'update_available') {
                titleText = tx('updateAvailableTitle');
                messageText = desktopUpdate
                  ? '将在系统浏览器中打开对应平台的安装包 / The platform download will open in your system browser.'
                  : tx('updateAvailableDetail');
                upgradeText = desktopUpdate ? '下载新版 / Download' : tx('updateButton');
                canUpgrade = true;
              } else if (state === 'upgrading') {
                titleText = tx('upgradingTitle');
                messageText = tx('upgradingMessage');
                upgradeText = tx('updatingButton');
              } else if (state === 'upgraded') {
                titleText = tx('upgradedTitle');
                messageText = tx('upgradedMessage');
                upgradeText = tx('upgradedTitle');
              } else if (state === 'failed') {
                titleText = tx('updateFailedTitle');
                messageText = data.message ? `${tx('updateFailedMessage')} ${String(data.message).slice(0, 180)}` : tx('updateFailedMessage');
              }
              if (title) title.textContent = titleText;
              if (message) message.textContent = messageText;
              if (upgradeButton) {
                upgradeButton.textContent = upgradeText;
                upgradeButton.disabled = !canUpgrade;
              }
              if (checkButton) {
                checkButton.textContent = state === 'checking' ? tx('checkingUpdate') : tx('checkAgain');
                checkButton.disabled = state === 'checking' || state === 'upgrading';
              }

              const latestKey = String(data.latest_version || '');
              const modal = document.getElementById('update-modal');
              if (state === 'update_available' && latestKey && UPDATE_AUTO_PROMPTED_VERSION !== latestKey && modal?.hidden) {
                UPDATE_AUTO_PROMPTED_VERSION = latestKey;
                setTimeout(() => openUpdateDialog(true), 0);
              }
            }

            async function refreshUpdateStatus(){
              try{
                const r = await fetch('/update_status');
                const j = await r.json();
                renderUpdateDialog(j.update || null);
              }catch(e){}
            }

            async function checkForUpdates(){
              try{
                renderUpdateDialog({
                  ...(LAST_UPDATE_STATUS || {}),
                  state:'checking',
                  current_version:LAST_UPDATE_STATUS?.current_version || document.body.dataset.appVersion
                });
                const r = await fetch('/update_check', {method:'POST'});
                const j = await r.json();
                renderUpdateDialog(j.update || null);
              }catch(e){
                renderUpdateDialog({
                  ...(LAST_UPDATE_STATUS || {}),
                  state:'failed',
                  message:String(e)
                });
              }
            }

            async function callUpgrade(){
              try{
                const button = document.getElementById('btn_upgrade');
                if (button) button.disabled = true;
                const r = await fetch('/upgrade', {method:'POST'});
                const j = await r.json();
                renderUpdateDialog(j.update || null);
              }catch(e){
                renderUpdateDialog({
                  ...(LAST_UPDATE_STATUS || {}),
                  state:'failed',
                  message:String(e)
                });
              }
            }

            function setMobileAccessState(state, title, message){
              const box = document.getElementById('mobile-access-state');
              if (box) box.dataset.state = state;
              setNodeText('#mobile-access-state-title', title);
              setNodeText('#mobile-access-state-message', message || '');
            }

            function mobileConnectionInfo(data, mode){
              const connections = data?.connections || {};
              if (connections[mode]) return connections[mode];
              if (mode === 'lan') {
                const urls = Array.isArray(data?.urls) ? data.urls : [];
                return {available:!!urls.length, online:!!urls.length, url:urls[0] || '', urls};
              }
              return {available:false, online:false, url:''};
            }

            function mobileConnectionIsAvailable(data, mode){
              const info = mobileConnectionInfo(data, mode);
              return !!(info.available && info.url && info.online !== false);
            }

            function mobileConnectionTitle(mode){
              if (mode === 'tailscale') return tx('mobileTailscaleTitle');
              if (mode === 'public') return tx('mobilePublicTitle');
              return tx('mobileLanTitle');
            }

            function renderMobileConnection(data, requestedMode=MOBILE_CONNECTION_MODE){
              const modes = ['lan', 'tailscale', 'public'];
              const selectedMode = requestedMode === 'public'
                ? 'public'
                : mobileConnectionIsAvailable(data, requestedMode)
                ? requestedMode
                : (modes.find(mode => mobileConnectionIsAvailable(data, mode)) || 'lan');
              MOBILE_CONNECTION_MODE = selectedMode;
              localStorage.setItem('toyoko-chan-mobile-connection-v1', selectedMode);

              modes.forEach(mode => {
                const button = document.querySelector(`[data-mobile-connection="${mode}"]`);
                const available = mobileConnectionIsAvailable(data, mode);
                if (button) {
                  button.disabled = !available && mode !== 'public';
                  button.classList.toggle('active', mode === selectedMode);
                  button.setAttribute('aria-pressed', mode === selectedMode ? 'true' : 'false');
                  button.dataset.online = available ? 'true' : 'false';
                }
                setNodeText(
                  `#mobile-${mode}-status`,
                  available ? tx('mobileAvailable') : (mode === 'public' ? tx('mobileNeedsSetup') : tx('mobileUnavailable'))
                );
              });

              const selected = mobileConnectionInfo(data, selectedMode);
              const url = selected.url || '';
              const urlInput = document.getElementById('mobile_access_url');
              const openLink = document.getElementById('btn_mobile_access_open');
              const qrWrap = document.getElementById('mobile-access-qr-wrap');
              const qrImage = document.getElementById('mobile_access_qr');
              if (urlInput) urlInput.value = url;
              if (urlInput) {
                urlInput.readOnly = selectedMode !== 'public';
                urlInput.placeholder = selectedMode === 'public' ? tx('mobilePublicPlaceholder') : '';
              }
              if (openLink) {
                openLink.href = url || '#';
                openLink.setAttribute('aria-disabled', url ? 'false' : 'true');
              }
              setNodeText('#mobile-access-qr-mode', mobileConnectionTitle(selectedMode));

              const showQr = !!(data.local_request && data.enabled && data.runtime_lan && url && data.qr_available);
              if (qrWrap) qrWrap.hidden = !showQr;
              if (qrImage && showQr) {
                qrImage.src = `/mobile_access_qr?connection=${encodeURIComponent(selectedMode)}&v=${encodeURIComponent(data.revision || Date.now())}`;
                qrImage.alt = tx('mobileQr');
              }

              const noteKey = selectedMode === 'tailscale' ? 'mobileTailscaleNote' : (selectedMode === 'public' ? 'mobilePublicNote' : 'mobileLanNote');
              const qrHelp = data.local_request && data.enabled && data.runtime_lan && !data.qr_available ? ` ${tx('mobileQrMissing')}` : '';
              setNodeText('#mobile-access-note', `${tx(noteKey)}${qrHelp}`);
            }

            function selectMobileConnection(mode){
              if (!LAST_MOBILE_ACCESS_STATUS || (mode !== 'public' && !mobileConnectionIsAvailable(LAST_MOBILE_ACCESS_STATUS, mode))) return;
              MOBILE_CONNECTION_MODE = mode;
              renderMobileConnection(LAST_MOBILE_ACCESS_STATUS, mode);
            }

            function renderMobileAccess(data){
              LAST_MOBILE_ACCESS_STATUS = data || null;
              if (!data) return;
              const toggle = document.getElementById('mobile_access_enabled');
              const controls = document.getElementById('mobile-access-host-controls');
              const details = document.getElementById('mobile-access-details');
              const codeInput = document.getElementById('mobile_access_code');
              if (toggle) toggle.checked = !!data.enabled;
              if (controls) controls.hidden = !data.local_request;
              if (details) details.hidden = !(data.local_request && data.enabled);
              if (codeInput) codeInput.value = data.pairing_code || '';

              if (!data.local_request) {
                setMobileAccessState('ready', tx('mobileRemote'), tx('mobileRemoteHelp'));
              } else if (data.restart_required) {
                setMobileAccessState('restart', tx('mobileRestart'), data.enabled ? tx('mobileRestartEnable') : tx('mobileRestartDisable'));
              } else if (data.enabled && data.runtime_lan) {
                setMobileAccessState('ready', tx('mobileReady'), tx('mobileReadyHelp'));
              } else {
                setMobileAccessState('idle', tx('mobileDisabled'), tx('mobileDisabledHelp'));
              }

              if (data.local_request) renderMobileConnection(data);
            }

            async function refreshMobileAccess(){
              try{
                setMobileAccessState('loading', tx('mobileLoading'), '');
                const response = await fetch('/mobile_access');
                const data = await response.json();
                if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
                renderMobileAccess(data);
              }catch(error){
                setMobileAccessState('error', tx('mobileError'), String(error));
              }
            }

            async function saveMobileAccess(rotate=false){
              const button = document.getElementById(rotate ? 'btn_mobile_access_rotate' : 'btn_mobile_access_apply');
              try{
                if (button) button.disabled = true;
                const response = await fetch('/mobile_access', {
                  method:'POST',
                  headers:{'Content-Type':'application/json'},
                  body:JSON.stringify({
                    enabled:document.getElementById('mobile_access_enabled')?.checked || false,
                    rotate:!!rotate,
                    restart:!rotate,
                    public_url:MOBILE_CONNECTION_MODE === 'public'
                      ? (document.getElementById('mobile_access_url')?.value || '').trim()
                      : (LAST_MOBILE_ACCESS_STATUS?.connections?.public?.configured_url || '')
                  })
                });
                const data = await response.json();
                if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
                renderMobileAccess(data);
                if (data.restart_scheduled) await waitForMobileRestart(!!data.enabled);
              }catch(error){
                setMobileAccessState('error', tx('mobileError'), String(error));
              }finally{
                if (button) button.disabled = false;
              }
            }

            function mobileRestartPause(milliseconds){
              return new Promise(resolve => setTimeout(resolve, milliseconds));
            }

            async function waitForMobileRestart(targetEnabled){
              setMobileAccessState('restart', tx('mobileRestarting'), tx('mobileRestartingHelp'));
              await mobileRestartPause(1000);
              const deadline = Date.now() + 20000;
              while (Date.now() < deadline) {
                try{
                  const response = await fetch(`/mobile_access?restart=${Date.now()}`, {cache:'no-store'});
                  if (response.ok) {
                    const data = await response.json();
                    if (data.ok && data.runtime_lan === targetEnabled && !data.restart_required) {
                      window.location.reload();
                      return true;
                    }
                  }
                }catch(error){}
                await mobileRestartPause(650);
              }
              setMobileAccessState('error', tx('mobileError'), tx('mobileRestartFailed'));
              return false;
            }

            async function copyMobileAccessUrl(){
              const value = document.getElementById('mobile_access_url')?.value || '';
              if (!value) return;
              try{
                await navigator.clipboard.writeText(value);
                setMobileAccessState('ready', tx('mobileCopied'), value);
              }catch(error){
                setMobileAccessState('error', tx('mobileError'), String(error));
              }
            }

            function registerServiceWorker(){
              if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
              navigator.serviceWorker.register('/service-worker.js').then(registration => {
                if (registration.waiting) registration.waiting.postMessage({type:'SKIP_WAITING'});
              }).catch(() => {});
            }

            function pwaStandalone(){
              return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
            }

            function updatePwaState(){
              const state = document.getElementById('pwa-state');
              const button = document.getElementById('btn_pwa_install');
              if (!state || !button) return;
              if (pwaStandalone()) {
                state.textContent = tx('pwaInstalled');
                button.hidden = true;
              } else if (PWA_INSTALL_PROMPT) {
                state.textContent = tx('pwaReady');
                button.hidden = false;
              } else {
                state.textContent = /iphone|ipad|ipod/i.test(navigator.userAgent) ? tx('pwaIos') : tx('pwaHelp');
                button.hidden = false;
              }
            }

            async function installPwa(){
              if (PWA_INSTALL_PROMPT) {
                PWA_INSTALL_PROMPT.prompt();
                await PWA_INSTALL_PROMPT.userChoice.catch(() => null);
                PWA_INSTALL_PROMPT = null;
              }
              updatePwaState();
            }

            const CAPABILITY_LABELS = {
              zh_cn:{area_search:'区域',radius_search:'方圆',availability:'空房',room_inventory:'数量',room_type:'房型',smoking:'吸烟',member_price:'会员价',hotel_info:'详情',coordinates:'坐标',conditional_http:'条件请求'},
              zh_tw:{area_search:'區域',radius_search:'方圓',availability:'空房',room_inventory:'數量',room_type:'房型',smoking:'吸菸',member_price:'會員價',hotel_info:'詳情',coordinates:'座標',conditional_http:'條件請求'},
              ja:{area_search:'地域',radius_search:'周辺',availability:'空室',room_inventory:'室数',room_type:'部屋',smoking:'喫煙',member_price:'会員料金',hotel_info:'詳細',coordinates:'座標',conditional_http:'条件リクエスト'},
              ko:{area_search:'지역',radius_search:'반경',availability:'객실',room_inventory:'수량',room_type:'객실형',smoking:'흡연',member_price:'회원가',hotel_info:'상세',coordinates:'좌표',conditional_http:'조건부 요청'},
              en:{area_search:'Area',radius_search:'Radius',availability:'Vacancy',room_inventory:'Count',room_type:'Room',smoking:'Smoking',member_price:'Member',hotel_info:'Info',coordinates:'Coords',conditional_http:'Conditional'}
            };

            async function loadProviderCapabilities(){
              const container = document.getElementById('provider-capability-table');
              if (!container) return;
              try {
                const response = await fetch('/api/v1/providers');
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const payload = await response.json();
                const matrix = payload.matrix || {};
                const capabilities = Array.isArray(matrix.capabilities) ? matrix.capabilities : [];
                const labels = CAPABILITY_LABELS[currentLang()] || CAPABILITY_LABELS.en;
                const providers = Array.isArray(matrix.providers) ? matrix.providers : [];
                container.innerHTML = `<table><thead><tr><th>Provider</th>${capabilities.map(key=>`<th title="${escText(key)}">${escText(labels[key] || key)}</th>`).join('')}</tr></thead><tbody>${providers.map(provider=>{
                  const name = currentLang() === 'en' ? provider.name_en : provider.name;
                  return `<tr><th><span class="source-badge ${escText(provider.id)}">${escText(name)}</span></th>${capabilities.map(key=>`<td class="${provider.capabilities?.[key] ? 'cap-yes' : 'cap-no'}">${provider.capabilities?.[key] ? '✓' : '—'}</td>`).join('')}</tr>`;
                }).join('')}</tbody></table>`;
              } catch (error) {
                container.textContent = String(error);
              }
            }

            function trendLocale(){
              return {zh_cn:'zh-CN',zh_tw:'zh-TW',ja:'ja-JP',ko:'ko-KR',en:'en-US'}[currentLang()] || 'en-US';
            }

            function trendDateTime(timestamp){
              const date = new Date(Number(timestamp || 0) * 1000);
              if (Number.isNaN(date.getTime())) return '—';
              return date.toLocaleString(trendLocale(), {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
            }

            function trendMoney(value){
              const amount = Number(value);
              return Number.isFinite(amount) && amount > 0 ? `¥${amount.toLocaleString(trendLocale())}` : '—';
            }

            function trendStatusMeta(value){
              if (value === true) return {cls:'available',label:tx('trendStatusAvailable'),icon:'✓'};
              if (value === false) return {cls:'unavailable',label:tx('trendStatusUnavailable'),icon:'×'};
              return {cls:'unknown',label:tx('trendStatusUnknown'),icon:'?'};
            }

            function trendHotelName(hotel){
              const code = String(hotel?.code || '');
              const result = LAST_RESULTS.find(item => String(item.code || '') === code);
              return hotel?.name || result?.name_primary || result?.name || result?.name_en || hotel?.display_code || code;
            }

            function renderTrends(data){
              LAST_TREND_DATA = data || null;
              const chart = document.getElementById('trend-chart');
              const overview = document.getElementById('trend-overview');
              const observations = document.getElementById('trend-observations');
              const summary = document.getElementById('trend-summary');
              const selector = document.getElementById('trend_hotel');
              if (!chart || !overview || !observations || !summary || !selector) return;
              const points = Array.isArray(data?.points) ? data.points : [];
              const hotels = (Array.isArray(data?.hotels) ? data.hotels : [])
                .filter(hotel => Number(hotel.samples || 0) > 0)
                .sort((left,right) => Number(right.latest_observed_at || 0) - Number(left.latest_observed_at || 0));
              summary.textContent = fmt('trendSelectedSummary', {count:points.length, hotels:hotels.length});
              const previousCode = selector.value;
              selector.innerHTML = hotels.map(hotel => {
                const label = `${hotel.display_code || hotel.code} · ${trendHotelName(hotel)}`;
                return `<option value="${escText(hotel.code)}">${escText(label)}</option>`;
              }).join('');
              const selectedHotel = hotels.find(hotel => String(hotel.code) === previousCode) || hotels[0];
              if (!selectedHotel) {
                chart.innerHTML = `<div class="trend-empty">${escText(tx('trendWaiting'))}</div>`;
                overview.innerHTML = '';
                observations.innerHTML = '';
                return;
              }
              selector.value = String(selectedHotel.code);
              const series = points
                .filter(point => String(point.code) === String(selectedHotel.code))
                .sort((left,right) => Number(left.ts || 0) - Number(right.ts || 0));
              const latestStatus = trendStatusMeta(selectedHotel.latest_available);
              const currentPrice = selectedHotel.current_price;
              const minPrice = trendMoney(selectedHotel.min_price);
              const maxPrice = trendMoney(selectedHotel.max_price);
              const known = Number(selectedHotel.known_samples || 0);
              const availableChecks = Number(selectedHotel.available_checks || 0);
              const rate = selectedHotel.availability_rate_percent;
              overview.innerHTML = `
                <div class="trend-metric status ${latestStatus.cls}"><span>${escText(tx('trendCurrentStatus'))}</span><strong>${latestStatus.icon} ${escText(latestStatus.label)}</strong><small>${escText(fmt('trendUpdated',{time:trendDateTime(selectedHotel.latest_observed_at)}))}</small></div>
                <div class="trend-metric"><span>${escText(tx('trendLatestPrice'))}</span><strong>${currentPrice ? escText(trendMoney(currentPrice)) : escText(tx('trendNoPrice'))}</strong><small>${escText(fmt('trendPriceRange',{min:minPrice,max:maxPrice}))}</small></div>
                <div class="trend-metric"><span>${escText(tx('trendHistoricalRate'))}</span><strong>${rate == null ? '—' : `${Number(rate)}%`}</strong><small>${escText(fmt('trendAvailableChecks',{available:availableChecks,known}))}</small></div>
                <div class="trend-metric"><span>${escText(tx('trendDataAmount'))}</span><strong>${Number(selectedHotel.samples || 0)}</strong><small>${escText(fmt('trendRecordsDetail',{count:selectedHotel.samples || 0,days:data?.days || 30}))}</small></div>`;
              if (!series.length) {
                chart.innerHTML = `<div class="trend-empty">${escText(tx('trendNoHotelHistory'))}</div>`;
                observations.innerHTML = '';
                return;
              }

              const width = 960, height = 205, left = 78, right = 18, priceTop = 22, priceBottom = 116;
              const statusY = 142, statusHeight = 20, plotWidth = width - left - right;
              const x = index => series.length === 1 ? left + plotWidth / 2 : left + index / (series.length - 1) * plotWidth;
              const priced = series.map((point,index) => ({point,index,price:Number(point.price)})).filter(item => Number.isFinite(item.price) && item.price > 0);
              const prices = priced.map(item => item.price);
              const minP = prices.length ? Math.min(...prices) : 0;
              const maxP = prices.length ? Math.max(...prices) : 0;
              const y = price => {
                if (!prices.length || minP === maxP) return (priceTop + priceBottom) / 2;
                return priceBottom - (price - minP) / (maxP - minP) * (priceBottom - priceTop);
              };
              const tickValues = !prices.length ? [] : minP === maxP ? [minP] : [maxP, Math.round((maxP + minP) / 2), minP];
              const grid = tickValues.map(price => `<line x1="${left}" y1="${y(price).toFixed(1)}" x2="${width-right}" y2="${y(price).toFixed(1)}" class="trend-grid-line"/><text x="${left-8}" y="${(y(price)+3).toFixed(1)}" text-anchor="end" class="trend-axis-label">${escText(trendMoney(price))}</text>`).join('');
              const pricePath = priced.length > 1 ? `<path d="${priced.map((item,index)=>`${index?'L':'M'}${x(item.index).toFixed(1)},${y(item.price).toFixed(1)}`).join(' ')}" class="trend-price-line"/>` : '';
              const pricePoints = priced.map(item => `<circle cx="${x(item.index).toFixed(1)}" cy="${y(item.price).toFixed(1)}" r="4" class="trend-price-point"><title>${escText(trendDateTime(item.point.ts))} · ${escText(trendMoney(item.price))}</title></circle>`).join('');
              const blockWidth = Math.max(4, Math.min(46, plotWidth / Math.max(1, series.length) - 4));
              const statusBlocks = series.map((point,index) => {
                const meta = trendStatusMeta(point.available);
                const detail = `${trendDateTime(point.ts)} · ${meta.label}${point.price ? ` · ${trendMoney(point.price)}` : ''}`;
                return `<rect x="${(x(index)-blockWidth/2).toFixed(1)}" y="${statusY}" width="${blockWidth.toFixed(1)}" height="${statusHeight}" rx="4" class="trend-availability-block ${meta.cls}"><title>${escText(detail)}</title></rect>`;
              }).join('');
              const firstTime = trendDateTime(series[0].ts);
              const lastTime = trendDateTime(series[series.length-1].ts);
              const timeLabels = series.length === 1
                ? `<text x="${x(0)}" y="188" text-anchor="middle" class="trend-axis-label">${escText(firstTime)}</text>`
                : `<text x="${left}" y="188" class="trend-axis-label">${escText(firstTime)}</text><text x="${width-right}" y="188" text-anchor="end" class="trend-axis-label">${escText(lastTime)}</text>`;
              chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escText(tx('trendTitle'))}">
                <text x="${left}" y="12" class="trend-axis-title">${escText(tx('trendPriceAxis'))}</text>${grid}${pricePath}${pricePoints}
                <text x="${left}" y="134" class="trend-axis-title">${escText(tx('trendAvailabilityAxis'))}</text>${statusBlocks}${timeLabels}
              </svg><div class="trend-legend"><span><i></i>${escText(tx('trendLegendPrice'))}</span><span class="available"><i></i>${escText(tx('trendLegendAvailable'))}</span><span class="unavailable"><i></i>${escText(tx('trendLegendUnavailable'))}</span><span class="unknown"><i></i>${escText(tx('trendLegendUnknown'))}</span><small>${escText(tx('trendEachBlock'))}</small></div>`;

              const recent = [...series].reverse().slice(0, 8);
              observations.innerHTML = `<div class="trend-observations-title">${escText(tx('trendRecentChecks'))}<span>${escText(trendHotelName(selectedHotel))}</span></div>
                <div class="trend-observation-list"><div class="trend-observation-row header"><span>${escText(tx('trendTime'))}</span><span>${escText(tx('trendStatus'))}</span><span>${escText(tx('trendPrice'))}</span><span>${escText(tx('trendRooms'))}</span><span>${escText(tx('trendRoomType'))}</span></div>
                ${recent.map(point => { const meta=trendStatusMeta(point.available); return `<div class="trend-observation-row"><span>${escText(trendDateTime(point.ts))}</span><span class="trend-status-chip ${meta.cls}">${meta.icon} ${escText(meta.label)}</span><span>${point.price?escText(trendMoney(point.price)):escText(tx('trendNoPrice'))}</span><span>${point.available===true?escText(fmt('trendRoomCount',{count:Number(point.room_count||0)})):'—'}</span><span title="${escText(point.room_type||'')}">${escText(point.room_type||tx('trendNoRoomType'))}</span></div>`; }).join('')}</div>`;
            }

            async function refreshTrends(force=false){
              const panel=document.getElementById('trend-panel');
              if (!force && (!panel?.open || Date.now()-LAST_TREND_REFRESH<60000)) return;
              const codes=LAST_RESULTS.map(result=>result.code).filter(Boolean).join(',');
              const days=document.getElementById('trend_days')?.value||30;
              try { const response=await fetch(`/api/v1/trends?codes=${encodeURIComponent(codes)}&days=${days}`); if(!response.ok)throw new Error(`HTTP ${response.status}`); const payload=await response.json(); renderTrends(payload.trends||{}); LAST_TREND_REFRESH=Date.now(); } catch(error) { const summary=document.getElementById('trend-summary'); if(summary)summary.textContent=String(error); }
            }

            async function refreshEventCenter(){
              const container=document.getElementById('event-center-list');
              if(!container)return;
              try{
                const response=await fetch('/api/v1/events?limit=50');
                if(!response.ok)throw new Error(`HTTP ${response.status}`);
                const payload=await response.json(); const events=Array.isArray(payload.events)?payload.events:[];
                if(!events.length){container.innerHTML=`<div class="trend-empty">${escText(tx('eventNone'))}</div>`;return;}
                container.innerHTML=events.map(event=>{
                  const detail=event.payload?.title||event.payload?.code||event.dedupe_key||'';
                  const deliveries=(event.deliveries||[]).map(item=>`<i>${escText(item.channel)} · ${escText(item.state)}</i>`).join('');
                  return `<div class="event-center-item"><strong>${escText(event.event_type)}</strong><div><span>${escText(detail)}</span><div class="event-deliveries">${deliveries}</div></div><time>${new Date(Number(event.created_at||0)*1000).toLocaleTimeString()}</time></div>`;
                }).join('');
              }catch(error){container.textContent=String(error);}
            }

            async function runSimulationStress(){
              const button=document.getElementById('btn_simulation_run'); const output=document.getElementById('simulation-output');
              if(!button||!output)return; setButtonBusy('btn_simulation_run',true); output.textContent='Running...';
              try { const response=await fetch('/api/v1/simulation/stress',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({iterations:Number(document.getElementById('simulation_iterations')?.value||500),concurrency:Number(document.getElementById('simulation_concurrency')?.value||4),scenario:'mixed'})}); const payload=await response.json(); if(!response.ok)throw new Error(payload.error||payload.message||`HTTP ${response.status}`); output.textContent=JSON.stringify(payload,null,2); } catch(error) { output.textContent=String(error); } finally { setButtonBusy('btn_simulation_run',false); }
            }

            function setRunning(is){
              const pill = document.getElementById('running-pill');
              const wasRunning = LAST_RUNNING;
              LAST_RUNNING = !!is;
              if (pill) {
                pill.textContent = is ? tx('running') : tx('stopped');
                pill.className = 'pill ' + (is ? 'on' : 'off');
              }
              const dockStatus = document.getElementById('dock-status');
              if (dockStatus) dockStatus.textContent = is ? tx('running') : tx('stopped');
              document.getElementById('command-dot')?.classList.toggle('running', !!is);
              document.getElementById('sidebar-status-dot')?.classList.toggle('running', !!is);
              document.querySelector('.nav-live-dot')?.classList.toggle('running', !!is);
              const sidebarStatus = document.getElementById('sidebar-status-text');
              if (sidebarStatus) sidebarStatus.textContent = is ? tx('running') : tx('stopped');
              const startButton = document.getElementById('btn_start');
              const stopButton = document.getElementById('btn_stop');
              const scanButton = document.getElementById('btn_scan_once');
              const defaultButton = document.getElementById('btn_default');
              if (startButton) startButton.textContent = is ? tx('restart') : tx('start');
              if (stopButton && stopButton.getAttribute('aria-busy') !== 'true') stopButton.disabled = !is;
              if (scanButton && scanButton.getAttribute('aria-busy') !== 'true') scanButton.disabled = !!is;
              if (defaultButton) defaultButton.disabled = !!is;
              if (!!is !== wasRunning) switchAppView(is ? 'monitor' : 'search', {instant:true});
            }

            function statusInfo(r, status){
                if (status === '❗' || r.requirement_unmet) return {cls:'warn', row:'', label:tx('check')};
                if (status === '✅' || r.available === true) return {cls:'available', row:'row-available', label:tx('available')};
                if (status === '❌' || r.available === false) return {cls:'unavailable', row:'row-unavailable', label:tx('unavailable')};
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

            function resultKind(result){
                if (result && result.available === true && !result.requirement_unmet) return 'available';
                if (result && result.available === false && !result.requirement_unmet) return 'unavailable';
                return 'check';
            }

            function resultPrice(result){
                const candidates = [
                    result?.min_member_price_text,
                    result?.min_price_text,
                    ...(Array.isArray(result?.offers_display)
                        ? result.offers_display.flatMap(offer => [offer.member_price_text, offer.price_text])
                        : [])
                ];
                for (const value of candidates){
                    const parsed = Number(String(value || '').replace(/[^0-9.]/g, ''));
                    if (Number.isFinite(parsed) && parsed > 0) return parsed;
                }
                return Number.POSITIVE_INFINITY;
            }

            function resultDistance(result){
                const hotel = AREA_HOTELS.find(item => String(item.code || '') === String(result?.code || ''));
                const distance = Number(hotel?.distance_km);
                return Number.isFinite(distance) ? distance : Number.POSITIVE_INFINITY;
            }

            function visibleResults(results){
                const query = RESULT_QUERY.trim().toLocaleLowerCase();
                let visible = results.filter(result => {
                    const matchesFilter = RESULT_FILTER === 'all'
                        || (RESULT_FILTER === 'changes'
                            ? RESULT_CHANGED_CODES.has(String(result.code || ''))
                            : resultKind(result) === RESULT_FILTER);
                    if (!matchesFilter) return false;
                    if (!query) return true;
                    const offers = Array.isArray(result.offers_display) ? result.offers_display : [];
                    const searchable = [
                        result.display_code, result.code, result.name, result.name_primary, result.name_en, result.name_zh,
                        result.name_zh_cn, result.name_zh_tw, result.name_ja, result.name_ko,
                        result.min_price_room, result.error_summary,
                        ...offers.flatMap(offer => [offer.room_title, offer.room_title_primary])
                    ].filter(Boolean).join(' ').toLocaleLowerCase();
                    return searchable.includes(query);
                });
                const kindRank = {available: 0, check: 1, unavailable: 2};
                visible = [...visible].sort((left, right) => {
                    if (RESULT_SORT === 'status') return kindRank[resultKind(left)] - kindRank[resultKind(right)];
                    if (RESULT_SORT === 'price') return resultPrice(left) - resultPrice(right);
                    if (RESULT_SORT === 'name') {
                        const leftName = left.name_primary || left.name_en || left.name || '';
                        const rightName = right.name_primary || right.name_en || right.name || '';
                        return String(leftName).localeCompare(String(rightName), currentLang().replace('_', '-'));
                    }
                    if (RESULT_SORT === 'distance') return resultDistance(left) - resultDistance(right);
                    return 0;
                });
                return visible;
            }

            function saveResultViewPrefs(){
                try {
                    localStorage.setItem(RESULT_VIEW_PREFS_KEY, JSON.stringify({
                        filter: RESULT_FILTER === 'changes' ? 'all' : RESULT_FILTER,
                        sort: RESULT_SORT,
                        query: RESULT_QUERY
                    }));
                } catch(e) {}
            }

            function restoreResultViewPrefs(){
                try {
                    const saved = JSON.parse(localStorage.getItem(RESULT_VIEW_PREFS_KEY) || '{}');
                    const filters = new Set(['all', 'available', 'unavailable', 'check']);
                    const sorts = new Set(['default', 'status', 'price', 'name', 'distance']);
                    if (filters.has(saved.filter)) RESULT_FILTER = saved.filter;
                    if (sorts.has(saved.sort)) RESULT_SORT = saved.sort;
                    RESULT_QUERY = typeof saved.query === 'string' ? saved.query.slice(0, 120) : '';
                } catch(e) {}
                const query = document.getElementById('result_query');
                const sort = document.getElementById('results_sort');
                if (query) query.value = RESULT_QUERY;
                if (sort) sort.value = RESULT_SORT;
            }

            function csvCell(value){
                return `"${String(value == null ? '' : value).replace(/"/g, '""')}"`;
            }

            function exportVisibleResults(){
                const results = visibleResults(Array.isArray(LAST_RESULTS) ? LAST_RESULTS : []);
                if (!results.length) {
                    document.getElementById('err').textContent = tx('exportNoResults');
                    document.getElementById('msg').textContent = '';
                    return;
                }
                const rows = [[
                    'Code', 'Hotel Primary', 'Hotel English', 'Status', 'Price', 'Member Price',
                    'Left', 'Room Type Primary', 'Room Type English', 'Smoking', 'Distance km',
                    'Checked At', 'Elapsed ms', 'Engine', 'Error', 'URL'
                ]];
                results.forEach(result => {
                    const offers = Array.isArray(result.offers_display) && result.offers_display.length
                        ? result.offers_display
                        : [{
                            price_text: result.min_price_text,
                            member_price_text: result.min_member_price_text,
                            remaining_norm: result.min_remaining,
                            room_title: result.min_price_room,
                            room_title_primary: ''
                        }];
                    offers.forEach(offer => {
                        const smoking = offer.room_smoking === 'smoking'
                            ? 'Smoking'
                            : (offer.room_smoking === 'non_smoking' ? 'Non-Smoking' : '');
                        const distance = resultDistance(result);
                        rows.push([
                            result.display_code || result.code || '', result.name_primary || result.name_zh || '', result.name_en || result.name || '',
                            resultKind(result), offer.price_text || '', offer.member_price_text || '', offer.remaining_norm || '',
                            offer.room_title_primary || '', offer.room_title || '', smoking,
                            Number.isFinite(distance) ? distance : '', result.checked_at || '', result.elapsed_ms ?? '',
                            result.engine_used || '', result.error_summary || '', result.url || ''
                        ]);
                    });
                });
                const csv = '\ufeff' + rows.map(row => row.map(csvCell).join(',')).join('\r\n');
                const blob = new Blob([csv], {type:'text/csv;charset=utf-8'});
                const link = document.createElement('a');
                const now = new Date();
                const stamp = now.toISOString().replace(/[-:]/g, '').slice(0, 15);
                link.href = URL.createObjectURL(blob);
                link.download = `toyoko-results-${stamp}.csv`;
                document.body.appendChild(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(link.href);
                document.getElementById('err').textContent = '';
            }

            function resultRoomCount(result){
                const values = Array.isArray(result?.offers_display) && result.offers_display.length
                    ? result.offers_display.map(offer => offer.remaining_norm)
                    : [result?.min_remaining];
                return values.reduce((total, value) => {
                    const parsed = Number(String(value || '').replace(/[^0-9]/g, ''));
                    return total + (Number.isFinite(parsed) ? parsed : 0);
                }, 0);
            }

            function detectResultChanges(previousResults, nextResults){
                const note = document.getElementById('result-change-note');
                RESULT_CHANGE_CLASSES = new Map();
                if (!Array.isArray(previousResults) || previousResults.length === 0) {
                    if (note) note.hidden = true;
                    return;
                }
                const previousByCode = new Map(previousResults.map(result => [String(result.code || ''), result]));
                const counts = {available: 0, unavailable: 0, count: 0};
                const changedCodes = new Set();
                nextResults.forEach(result => {
                    const code = String(result.code || '');
                    const previous = previousByCode.get(code);
                    if (!previous) return;
                    const previousKind = resultKind(previous);
                    const nextKind = resultKind(result);
                    if (previousKind !== 'available' && nextKind === 'available') {
                        counts.available += 1;
                        changedCodes.add(code);
                        RESULT_CHANGE_CLASSES.set(code, 'result-new-available');
                    } else if (previousKind === 'available' && nextKind !== 'available') {
                        counts.unavailable += 1;
                        changedCodes.add(code);
                        RESULT_CHANGE_CLASSES.set(code, 'result-lost-available');
                    } else if (nextKind === 'available' && resultRoomCount(previous) !== resultRoomCount(result)) {
                        counts.count += 1;
                        changedCodes.add(code);
                        RESULT_CHANGE_CLASSES.set(code, 'result-count-changed');
                    }
                });
                const messages = [];
                if (counts.available) messages.push(fmt('resultBecameAvailable', {count: counts.available}));
                if (counts.unavailable) messages.push(fmt('resultNoLongerAvailable', {count: counts.unavailable}));
                if (counts.count) messages.push(fmt('resultRoomCountChanged', {count: counts.count}));
                if (note) {
                    note.textContent = messages.join(' · ');
                    note.hidden = messages.length === 0;
                }
                if (messages.length) {
                    RESULT_CHANGED_CODES = changedCodes;
                    RESULT_CHANGE_TOKEN += 1;
                }
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
                    const age = (typeof item.age_sec === 'number' && item.state !== 'disabled')
                        ? ` · ${fmt('secondsAgo', {seconds:item.age_sec})}` : '';
                    const msg = item.message ? `${safe(localizedMessage(item.message))}${age}` : (item.enabled ? `${safe(tx('waitingTrigger'))}${age}` : safe(tx('notEnabled')));
                    return `<div class="push-card">
                        <div class="push-name">${safe(channelName(item.key, item.label_en))}</div>
                        <div class="push-enabled">${enabledText}</div>
                        <span class="push-chip ${safe(state)}">${stateLabel[state] || stateLabel.waiting}</span>
                        <div class="push-message" title="${safe(msg)}">${msg}</div>
                    </div>`;
                }).join('');
            }

            function renderRows(results, force=false){
                const incoming = Array.isArray(results);
                if (incoming) {
                    const fingerprint = JSON.stringify(results);
                    if (!force && fingerprint === LAST_RESULTS_FINGERPRINT) return;
                    detectResultChanges(LAST_RESULTS, results);
                    LAST_RESULTS = results;
                    LAST_RESULTS_FINGERPRINT = fingerprint;
                    try { localStorage.setItem(OFFLINE_RESULTS_KEY, JSON.stringify({saved_at:Date.now(),results})); } catch(error) {}
                } else {
                    force = true;
                }
                const sourceResults = Array.isArray(LAST_RESULTS) ? LAST_RESULTS : [];
                const displayedResults = visibleResults(sourceResults);
                const tbody = document.getElementById('results-body');
                const membership = document.getElementById('membership_status')?.value || 'member';
                const safe = (s) => String(s || '').replace(/[&<>"']/g, (m) => ({
                    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
                }[m]));
                const hotelNameHtml = (r) => {
                    const primary = r.name_primary || r.name_zh || '';
                    const en = r.name_en || r.name || '(Hotel name not found)';
                    const inner = safe(bilingualText(primary, en));
                    const triggerClass = 'hotel-info-trigger';
                    const source = providerShort(r.provider || 'toyoko');
                    return `<a class="${triggerClass}" data-hotel-code="${safe(r.code)}" href="${safe(r.url)}" target="_blank" rel="noreferrer noopener">${inner}</a><span class="source-badge ${safe(r.provider || 'toyoko')}">${safe(source)}</span>`;
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
                const telemetryHtmlFor = (result) => {
                    const parts = [];
                    if (result.engine_used) parts.push(String(result.engine_used).toUpperCase());
                    if (Number.isFinite(Number(result.elapsed_ms))) {
                        const elapsed = Number(result.elapsed_ms);
                        parts.push(elapsed >= 1000 ? `${(elapsed / 1000).toFixed(1)}s` : `${elapsed}ms`);
                    }
                    if (result.checked_at) {
                        const checked = new Date(result.checked_at);
                        if (!Number.isNaN(checked.getTime())) {
                            parts.push(checked.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'}));
                        }
                    }
                    let cacheBadge = '';
                    if (result.cache_fallback) {
                        cacheBadge = `<span class="result-cache fallback">${safe(tx('cacheFallback'))}</span>`;
                    } else if (result.cache_validated) {
                        cacheBadge = `<span class="result-cache validated">${safe(tx('cacheValidated'))}</span>`;
                    } else if (result.from_cache) {
                        cacheBadge = `<span class="result-cache">${safe(fmt('cacheFresh', {age:Math.max(0, Number(result.cache_age_sec || 0))}))}</span>`;
                    }
                    const meta = (parts.length || cacheBadge) ? `<div class="result-telemetry">${safe(parts.join(' · '))}${cacheBadge}</div>` : '';
                    const error = result.error_summary
                        ? `<div class="result-error" title="${safe(result.error_summary)}">${safe(result.error_summary)}</div>`
                        : '';
                    return meta + error;
                };
                setResultStats(sourceResults);
                const count = document.getElementById('results_filter_count');
                if (count) count.textContent = fmt('showingResults', {shown: displayedResults.length, total: sourceResults.length});
                document.querySelectorAll('[data-result-filter]').forEach(button => {
                    const active = button.dataset.resultFilter === RESULT_FILTER;
                    button.classList.toggle('active', active);
                    button.setAttribute('aria-pressed', active ? 'true' : 'false');
                });
                if (sourceResults.length === 0){
                    tbody.innerHTML = `<tr><td colspan="6" class="empty-results">${safe(tx('noData'))}</td></tr>`;
                    return;
                }
                if (displayedResults.length === 0){
                    tbody.innerHTML = `<tr><td colspan="6" class="empty-results">${safe(tx('noFilteredResults'))}</td></tr>`;
                    return;
                }

                const rows = [];

                displayedResults.forEach(r => {
                    const nameHtml  = hotelNameHtml(r);

                    // 生成一行的帮助函数：是否显示Code/Name由首行决定
                    const addRow = (showCode, showName, status, priceHtml, leftHtml, roomHtml) => {
                        const info = statusInfo(r, status);
                        const statusHtml = status ? `<span class="status-badge ${info.cls}">${status} ${info.label}</span>` : '';
                        const telemetryHtml = showCode ? telemetryHtmlFor(r) : '';
                        const changeClass = RESULT_CHANGE_CLASSES.get(String(r.code || '')) || '';
                        rows.push(
                            `<tr class="${info.row} ${changeClass}">
                              <td class="code-cell">${showCode ? safe(r.display_code || r.code) : ''}</td>
                              <td class="hotel-cell">${showName ? nameHtml : ''}</td>
                              <td>${statusHtml}${telemetryHtml}</td>
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
                if (RESULT_CHANGE_CLASSES.size) {
                    const changeToken = RESULT_CHANGE_TOKEN;
                    setTimeout(() => {
                        if (changeToken !== RESULT_CHANGE_TOKEN) return;
                        document.querySelectorAll('.result-new-available,.result-lost-available,.result-count-changed').forEach(row => {
                            row.classList.remove('result-new-available', 'result-lost-available', 'result-count-changed');
                        });
                        const note = document.getElementById('result-change-note');
                        if (note) note.hidden = true;
                        RESULT_CHANGE_CLASSES.clear();
                    }, 8000);
                }
            }

            function restoreOfflineResults(){
              if (LAST_RESULTS.length) return;
              try {
                const snapshot=JSON.parse(localStorage.getItem(OFFLINE_RESULTS_KEY)||'null');
                if(snapshot&&Array.isArray(snapshot.results)){
                  LAST_RESULTS=snapshot.results;
                  LAST_RESULTS_FINGERPRINT=JSON.stringify(snapshot.results);
                }
              } catch(error) {}
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

            async function refreshResultsDelta(serverRevision, force=false){
              const revision = Number(serverRevision);
              if (!force && Number.isFinite(revision) && revision === RESULTS_REVISION) return;
              const since = force ? -1 : RESULTS_REVISION;
              const response = await fetch(`/api/v1/results?since=${encodeURIComponent(since)}`);
              if (!response.ok) throw new Error(`HTTP ${response.status}`);
              const payload = await response.json();
              if (payload.changed) renderRows(payload.results || []);
              RESULTS_REVISION = Number(payload.revision ?? revision ?? RESULTS_REVISION);
            }

            async function refreshAvailabilityLogsDelta(serverRevision, force=false){
              const revision = Number(serverRevision);
              if (!force && Number.isFinite(revision) && revision === AVAILABILITY_LOGS_REVISION) return;
              const since = force ? -1 : AVAILABILITY_LOGS_REVISION;
              const response = await fetch(`/api/v1/availability-logs?since=${encodeURIComponent(since)}`);
              if (!response.ok) throw new Error(`HTTP ${response.status}`);
              const payload = await response.json();
              if (payload.changed) renderAvailabilityLogs(payload.availability_logs || []);
              AVAILABILITY_LOGS_REVISION = Number(payload.revision ?? revision ?? AVAILABILITY_LOGS_REVISION);
            }

            async function refreshCatalogSnapshots(){
              if (CATALOG_REFRESH_IN_FLIGHT || document.hidden) return;
              CATALOG_REFRESH_IN_FLIGHT = true;
              try {
                const [catalogResponse, providerResponse] = await Promise.all([
                  fetch('/hotel_catalog_status'),
                  fetch('/provider_catalog_status')
                ]);
                if (catalogResponse.ok) {
                  const payload = await catalogResponse.json();
                  renderHotelCatalog(payload.catalog || null);
                }
                if (providerResponse.ok) {
                  const payload = await providerResponse.json();
                  renderProviderCatalog(payload || null);
                }
              } catch(e) {
                // The lightweight runtime heartbeat remains the connection authority.
              } finally {
                CATALOG_REFRESH_IN_FLIGHT = false;
              }
            }

            async function refreshStatus(manual=false){
              if (STATUS_REFRESH_IN_FLIGHT || (document.hidden && !manual)) return null;
              STATUS_REFRESH_IN_FLIGHT = true;
              if (manual) setButtonBusy('btn_results_refresh', true);
              try{
                const endpoint = STATUS_BOOTSTRAPPED ? '/api/v1/runtime' : '/status';
                let r = await fetch(endpoint);
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                let j = await r.json();
                if (endpoint !== '/status' && SERVER_INSTANCE_ID && j.instance_id !== SERVER_INSTANCE_ID) {
                  r = await fetch('/status');
                  if (!r.ok) throw new Error(`HTTP ${r.status}`);
                  j = await r.json();
                  RESULTS_REVISION = -1;
                  AVAILABILITY_LOGS_REVISION = -1;
                }
                SERVER_INSTANCE_ID = String(j.instance_id || SERVER_INSTANCE_ID);
                setConnectionOnline(true);
                setRunning(!!j.running);
                renderProgress(j.progress);
                if (j && j.config){
                  LAST_CONFIG = j.config;
                  setIfNotFocused('start_date', j.config.start_date);
                  setIfNotFocused('end_date', j.config.end_date);
                  setIfNotFocused('people', j.config.people);
                  setIfNotFocused('rooms', j.config.rooms);
                  setIfNotFocused('smoking', j.config.smoking);
                  setIfNotFocused('room_requirement', (j.config.room_requirement || j.config.om_requirement || 'any'));
                  setIfNotFocused('membership_status', j.config.membership_status || 'member');
                  const activeProviders = Array.isArray(j.config.enabled_providers) ? j.config.enabled_providers : DEFAULT_PROVIDER_IDS;
                  PROVIDER_IDS.forEach(provider => {
                    const checkbox = document.getElementById(`provider_${provider}`);
                    if (checkbox && !recentlyEdited(`provider_${provider}`) && !BLOCK_REMOTE_OVERWRITE) checkbox.checked = activeProviders.includes(provider);
                  });
                  setIfNotFocused('engine', j.config.engine || 'http');
                  setIfNotFocused('smart_parallel_workers', j.config.smart_parallel_workers || 1);
                  const elParallel = document.getElementById('smart_parallel_enabled');
                  if (elParallel && !recentlyEdited('smart_parallel_enabled') && !BLOCK_REMOTE_OVERWRITE) elParallel.checked = !!j.config.smart_parallel_enabled;
                  const elBackoff = document.getElementById('adaptive_backoff_enabled');
                  if (elBackoff && !recentlyEdited('adaptive_backoff_enabled') && !BLOCK_REMOTE_OVERWRITE) elBackoff.checked = j.config.adaptive_backoff_enabled !== false;

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
                if (Array.isArray(j.results)) {
                  renderRows(j.results);
                  RESULTS_REVISION = Number(j.results_revision ?? RESULTS_REVISION);
                } else {
                  await refreshResultsDelta(j.results_revision, manual);
                }
                if (Array.isArray(j.availability_logs)) {
                  renderAvailabilityLogs(j.availability_logs);
                  AVAILABILITY_LOGS_REVISION = Number(j.availability_logs_revision ?? AVAILABILITY_LOGS_REVISION);
                } else {
                  await refreshAvailabilityLogsDelta(j.availability_logs_revision, manual);
                }
                renderPushStatus(j.notification_status || []);
                renderProviderHealth(j.provider_health || {});
                renderDiagnostics(j.diagnostics || {});
                renderHomeDashboard(j);
                if ('hotel_catalog' in j) renderHotelCatalog(j.hotel_catalog || null);
                if ('provider_catalog' in j) renderProviderCatalog(j.provider_catalog || null);
                const act = (j && j.action) ? j.action : '(idle)';
                const age = (j && (typeof j.action_age_sec === 'number')) ? j.action_age_sec : null;
                const actLine = `${tx('currentAction')}: ${act}${age!=null ? ` (${age}s ago)` : ''}`;
                const actEl = document.getElementById('action-text');
                if (actEl) actEl.textContent = actLine;
                STATUS_BOOTSTRAPPED = true;
                STATUS_FAILURES = 0;
                LAST_STATUS_UPDATED_AT = new Date();
                updateResultsTimestamp();
                if (document.getElementById('trend-panel')?.open) refreshTrends();
                if (document.getElementById('event-center-panel')?.open) refreshEventCenter();
                return true;
              }catch(e){
                STATUS_FAILURES += 1;
                setConnectionOnline(false);
                if (manual) {
                  document.getElementById('err').textContent = tx('connectionOffline');
                  document.getElementById('msg').textContent = '';
                }
                return false;
              }finally{
                STATUS_REFRESH_IN_FLIGHT = false;
                if (manual) setButtonBusy('btn_results_refresh', false);
              }
            }

            function scheduleStatusReconnect(delay){
              if (STATUS_RECONNECT_TIMER) clearTimeout(STATUS_RECONNECT_TIMER);
              STATUS_RECONNECT_TIMER=setTimeout(runStatusLoop,Math.max(250,Number(delay)||2000));
            }

            async function runStatusLoop(){
              const result=await refreshStatus(false);
              if(result===false){
                const backoff=Math.min(30000,1000*Math.pow(2,Math.min(5,STATUS_FAILURES)));
                scheduleStatusReconnect(backoff*(0.85+Math.random()*0.3));
              }else{
                scheduleStatusReconnect(document.hidden?8000:2000);
              }
            }

            document.getElementById('btn_scan_once').addEventListener('click', (e)=>{e.preventDefault(); callStart(true);});
            document.getElementById('btn_start').addEventListener('click', (e)=>{e.preventDefault(); callStart(false);});
            document.getElementById('btn_stop').addEventListener('click', (e)=>{e.preventDefault(); callStop();});
            document.querySelectorAll('[data-result-filter]').forEach(button => {
              button.addEventListener('click', (event) => {
                event.preventDefault();
                RESULT_FILTER = button.dataset.resultFilter || 'all';
                saveResultViewPrefs();
                renderRows();
              });
            });
            const resultSort = document.getElementById('results_sort');
            if (resultSort) resultSort.addEventListener('change', () => {
              RESULT_SORT = resultSort.value || 'default';
              saveResultViewPrefs();
              renderRows();
            });
            const resultQuery = document.getElementById('result_query');
            if (resultQuery) resultQuery.addEventListener('input', () => {
              RESULT_QUERY = resultQuery.value || '';
              saveResultViewPrefs();
              renderRows();
            });
            const resultRefresh = document.getElementById('btn_results_refresh');
            if (resultRefresh) resultRefresh.addEventListener('click', (event) => {
              event.preventDefault();
              refreshStatus(true);
            });
            const resultExport = document.getElementById('btn_results_export');
            if (resultExport) resultExport.addEventListener('click', (event) => {
              event.preventDefault();
              exportVisibleResults();
            });
            document.getElementById('btn_trend_refresh')?.addEventListener('click', event=>{event.preventDefault();refreshTrends(true);});
            document.getElementById('trend_hotel')?.addEventListener('change', ()=>{if(LAST_TREND_DATA)renderTrends(LAST_TREND_DATA);});
            document.getElementById('trend_days')?.addEventListener('change', ()=>refreshTrends(true));
            document.getElementById('trend-panel')?.addEventListener('toggle', event=>{if(event.currentTarget.open)refreshTrends(true);});
            document.getElementById('event-center-panel')?.addEventListener('toggle', event=>{if(event.currentTarget.open)refreshEventCenter();});
            document.getElementById('btn_pwa_install')?.addEventListener('click', event=>{event.preventDefault();installPwa();});
            document.getElementById('btn_simulation_run')?.addEventListener('click', event=>{event.preventDefault();runSimulationStress();});
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
            const updateCheckButton = document.getElementById('btn_update_check');
            if (updateCheckButton) updateCheckButton.addEventListener('click', (e)=>{e.preventDefault(); checkForUpdates();});
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
            const areaSort = document.getElementById('area_sort');
            if (areaSort) areaSort.addEventListener('change', () => {
              AREA_SORT = areaSort.value || 'default';
              renderAreaHotels();
            });
            const selectedOnlyButton = document.getElementById('btn_area_selected_only');
            if (selectedOnlyButton) selectedOnlyButton.addEventListener('click', (event) => {
              event.preventDefault();
              AREA_SELECTED_ONLY = !AREA_SELECTED_ONLY;
              selectedOnlyButton.classList.toggle('active', AREA_SELECTED_ONLY);
              selectedOnlyButton.setAttribute('aria-pressed', AREA_SELECTED_ONLY ? 'true' : 'false');
              renderAreaHotels();
            });
            document.querySelectorAll('[data-hotel-workspace-view]').forEach(button => {
              button.addEventListener('click', () => setHotelWorkspaceView(button.dataset.hotelWorkspaceView));
            });
            document.querySelectorAll('.step-button[data-step-target]').forEach(button => {
              button.addEventListener('click', () => {
                const input = document.getElementById(button.dataset.stepTarget || '');
                if (!input) return;
                const delta = Number(button.dataset.stepDelta || 0);
                const minimum = Number(input.min || Number.NEGATIVE_INFINITY);
                const maximum = Number(input.max || Number.POSITIVE_INFINITY);
                input.value = String(Math.min(maximum, Math.max(minimum, Number(input.value || minimum) + delta)));
                input.dispatchEvent(new Event('input', {bubbles:true}));
                input.dispatchEvent(new Event('change', {bubbles:true}));
              });
            });
            document.querySelectorAll('input[name="hotel_picker_mode"]').forEach(el => {
              el.addEventListener('change', () => {
	                setPickerMode(currentSearchMode());
	                AREA_HOTELS = [];
	                AREA_SELECTED_CODES = null;
	                renderAreaHotels();
                markEdited('hotel_picker_mode');
                BLOCK_REMOTE_OVERWRITE = true;
              });
            });
            const primaryLanguage = document.getElementById('primary_language');
            if (primaryLanguage) primaryLanguage.addEventListener('change', ()=>{
              storageSet(LANGUAGE_KEY, primaryLanguage.value || 'zh_cn');
              hideHotelInfoNow();
              applyUiLanguage();
              loadProviderCapabilities();
              updatePwaState();
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
            const btnProviderAll = document.getElementById('btn_provider_all');
            if (btnProviderAll) btnProviderAll.addEventListener('click', (event) => {
              event.preventDefault();
              PROVIDER_IDS.forEach(provider => {
                const checkbox = document.getElementById(`provider_${provider}`);
                if (checkbox) checkbox.checked = true;
              });
              AREA_HOTELS = [];
              AREA_SELECTED_CODES = null;
              renderAreaHotels();
              syncProviderAllButton();
              setAreaStatus(tx('areaHint'));
              markEdited('enabled_providers');
              BLOCK_REMOTE_OVERWRITE = true;
            });
            PROVIDER_IDS.forEach(provider => {
              const checkbox = document.getElementById(`provider_${provider}`);
              if (checkbox) checkbox.addEventListener('change', () => {
                if (!enabledProviders().length) checkbox.checked = true;
                AREA_HOTELS = [];
                AREA_SELECTED_CODES = null;
                renderAreaHotels();
                setAreaStatus(tx('areaHint'));
                syncProviderAllButton();
                markEdited(`provider_${provider}`);
                BLOCK_REMOTE_OVERWRITE = true;
              });
            });
            const btnCatalogRefresh = document.getElementById('btn_catalog_refresh');
            if (btnCatalogRefresh) btnCatalogRefresh.addEventListener('click', (e)=>{ e.preventDefault(); refreshHotelCatalog(); });
            const btnCatalogAck = document.getElementById('btn_catalog_ack');
            if (btnCatalogAck) btnCatalogAck.addEventListener('click', (e)=>{ e.preventDefault(); acknowledgeNewHotels(); });
            const btnCacheClear = document.getElementById('btn_cache_clear');
            if (btnCacheClear) btnCacheClear.addEventListener('click', async (event) => {
              event.preventDefault();
              setButtonBusy('btn_cache_clear', true);
              try {
                const response = await fetch('/api/v1/cache/clear', {method:'POST'});
                const payload = await response.json();
                if (!response.ok || !payload.ok) throw new Error(payload.message || `HTTP ${response.status}`);
                const removed = Math.max(0, Number(payload.removed || 0));
                const msg = document.getElementById('msg');
                if (msg) msg.textContent = fmt('cacheCleared', {count:removed});
                renderDiagnostics({...LAST_DIAGNOSTICS, cache_entries:0, cache_fresh_entries:0, cache_hit_rate_percent:0});
              } catch (error) {
                const err = document.getElementById('err');
                if (err) err.textContent = String(error);
              } finally {
                setButtonBusy('btn_cache_clear', false);
              }
            });
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
              if (langEl) {
                langEl.value = 'zh_cn';
                storageSet(LANGUAGE_KEY, 'zh_cn');
              }
              PROVIDER_IDS.forEach(name => {
                const provider = document.getElementById(`provider_${name}`);
                if (provider) provider.checked = DEFAULT_PROVIDER_IDS.includes(name);
              });
              applyUiLanguage();
              const engineEl = document.getElementById('engine');
              if (engineEl) engineEl.value = 'http';
	              AREA_HOTELS = [];
	              AREA_SELECTED_CODES = null;
	              renderAreaHotels();
              ['enable_telegram','enable_local','enable_email','enable_bark','enable_serverchan','smart_parallel_enabled','bark_critical_enabled'].forEach(id=>{
                const c = document.getElementById(id); if (c) c.checked = false;
              });
              const adaptiveBackoff = document.getElementById('adaptive_backoff_enabled');
              if (adaptiveBackoff) adaptiveBackoff.checked = true;
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
              AREA_SELECTED_ONLY = false;
              AREA_SORT = 'default';
              const selectedOnly = document.getElementById('btn_area_selected_only');
              if (selectedOnly) {
                selectedOnly.classList.remove('active');
                selectedOnly.setAttribute('aria-pressed', 'false');
              }
              const areaSort = document.getElementById('area_sort');
              if (areaSort) areaSort.value = 'default';
              syncProviderAllButton();
              setPickerMode('area');
              setHotelWorkspaceView('list');
              syncDisplayValues();
              updateAreaSelectionSummary();
              markEdited('defaults');
              BLOCK_REMOTE_OVERWRITE = true;
            });
            window.addEventListener('beforeunload', (event) => {
              if (!FORM_DIRTY) return;
              event.preventDefault();
              event.returnValue = '';
            });
            document.addEventListener('visibilitychange', () => {
              if (!document.hidden) {
                scheduleStatusReconnect(50);
                refreshCatalogSnapshots();
              }
            });
            window.addEventListener('online',()=>{setConnectionOnline(true);STATUS_FAILURES=0;scheduleStatusReconnect(50);});
            window.addEventListener('offline',()=>{setConnectionOnline(false);scheduleStatusReconnect(2000);});
            window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();PWA_INSTALL_PROMPT=event;updatePwaState();});
            window.addEventListener('appinstalled',()=>{PWA_INSTALL_PROMPT=null;updatePwaState();});
            restoreResultViewPrefs();
            initAnimatedDetails();
            initHotelInfoPreview();
            updateAreaSelectionSummary();
            restoreOfflineResults();
            renderRows();
            runStatusLoop();
            refreshSearchHistory();
            refreshUpdateStatus();
            refreshMobileAccess();
            loadProviderCapabilities();
            updatePwaState();
            registerServiceWorker();
            setInterval(refreshCatalogSnapshots, 30000);
            setInterval(refreshUpdateStatus, 10000);
