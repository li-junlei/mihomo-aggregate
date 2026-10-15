/* UI translations only. Config values and subscription group names remain unchanged. */
const PanelI18n = (() => {
  const en = {
  "Mihomo Aggregate · 订阅管理": "Mihomo Aggregate · Subscription Manager",
  "主导航": "Main navigation",
  "仪表盘": "Dashboard",
  "节点管理": "Nodes",
  "设置": "Settings",
  "订阅管理 · 在这里维护机场，分享链接始终不变。": "Manage your providers here. Your shared subscription URL stays the same.",
  "读取中": "Loading",
  "更新全部": "Update all",
  "订阅概况": "Subscription overview",
  "发布节点": "Published nodes",
  "最近检测可用": "Healthy at last check",
  "最近完成": "Last completed",
  "我的机场": "My providers",
  "单击展开操作 · 拖动右上角调整顺序": "Click for actions · Drag the top-right handle to reorder",
  "机场订阅": "Provider subscriptions",
  "固定分享链接": "Permanent subscription URL",
  "复制链接": "Copy URL",
  "查看节点详情，管理订阅发布范围。": "View node details and choose which nodes to publish.",
  "检查全部节点": "Check all nodes",
  "搜索节点名称": "Search node names",
  "全部机场": "All providers",
  "全部地区": "All regions",
  "全部协议": "All protocols",
  "全部状态": "All statuses",
  "排序": "Sort",
  "按名称排序": "Sort by name",
  "延迟从低到高": "Lowest latency first",
  "清空筛选": "Clear filters",
  "排除当前筛选结果（0）": "Exclude filtered nodes (0)",
  "恢复当前筛选结果（0）": "Restore filtered nodes (0)",
  "仅解除手动排除，持续排除规则仍然生效": "Remove manual exclusions only; persistent rules still apply",
  "延迟来自服务器最近检测，不代表当前设备的连接速度。列表筛选不改变订阅；排除会影响发布，但保留缓存。": "Latency comes from the server's last check and does not reflect this device's connection speed. Filters only change the view; exclusions change publication while keeping cached nodes.",
  "节点列表，可在区域内滚动": "Node list, scroll within this region",
  "节点 / 机场": "Node / Provider",
  "地区 / 协议": "Region / Protocol",
  "最近延迟": "Last latency",
  "发布状态": "Publication status",
  "操作": "Actions",
  "持续排除规则": "Persistent exclusion rules",
  "可组合机场、地区、协议和名称关键词。同一规则需同时满足所选条件，任意已开启的规则命中即排除；关闭开关可暂停规则，保留条件。以后新增的匹配节点也会被排除。": "Combine provider, region, protocol and name keywords. All conditions in a rule must match; any enabled matching rule excludes a node. Disable a rule to pause it while keeping its conditions. Future matching nodes are also excluded.",
  "作用机场": "Provider",
  "地区": "Region",
  "协议": "Protocol",
  "节点名称包含（可选）": "Node name contains (optional)",
  "例如：高倍率": "e.g. premium",
  "添加规则": "Add rule",
  "当前匹配 0 个节点": "Currently matches 0 nodes",
  "更新计划与生成的订阅配置。": "Update schedules and generated subscription settings.",
  "更新设置": "Update settings",
  "正常拉取间隔（分钟）": "Fetch interval (minutes)",
  "节点检测间隔（分钟）": "Health check interval (minutes)",
  "分流规则读取中": "Loading routing rules",
  "保存间隔": "Save intervals",
  "订阅配置": "Subscription settings",
  "按国家 / 地区分组": "Group by country / region",
  "设置地区": "Choose regions",
  "读取分组设置中": "Loading group settings",
  "关闭后仍保留全局 AUTO 测速组和节点选择。": "The global AUTO latency group and node selection remain available when disabled.",
  "生成 ChatGPT 测速组": "Generate ChatGPT latency group",
  "使用 https://chatgpt.com/ 测速，包含全部节点，可在客户端 PROXY 中选择 ChatGPT。": "Tests all nodes against https://chatgpt.com/. Select ChatGPT under PROXY in your client.",
  "测速响应不代表账号登录或对话一定可用。": "A successful latency check does not guarantee that login or conversations will work.",
  "保存后后台重新生成订阅，客户端更新订阅后生效。": "Saving regenerates the subscription in the background. Update the subscription in your client to apply it.",
  "保存配置": "Save settings",
  "编辑机场": "Edit provider",
  "关闭": "Close",
  "机场名称": "Provider name",
  "例如 Ytoo": "e.g. Ytoo",
  "机场 ID": "Provider ID",
  "机场官网（可选）": "Provider website (optional)",
  "HTTPS 订阅地址": "HTTPS subscription URL",
  "拉取代理（留空为直连）": "Fetch proxy (leave blank for direct access)",
  "显示 / 隐藏地址": "Show / hide URLs",
  "客户端标识": "User-Agent",
  "启用机场": "Enable provider",
  "移除机场": "Remove provider",
  "取消": "Cancel",
  "保存并更新": "Save and update",
  "国家 / 地区分组": "Country / region groups",
  "关闭地区设置": "Close region settings",
  "只显示当前启用机场订阅中已有的地区。选中的地区单独成组，其余节点归入“🌐 其他国家”。": "Only regions in enabled providers are shown. Selected regions get their own groups; remaining nodes go into the “🌐 其他国家” group.",
  "全部地区单独分组": "Create a group for every region",
  "包含以后新增的地区": "Include regions added in the future",
  "暂无可选地区，请先更新机场订阅。": "No regions available. Update provider subscriptions first.",
  "暂时没有节点的已选地区会保留设置；取消全部地区可清空选择。": "Selected regions without nodes keep their settings. Turn off all regions to clear the selection.",
  "应用选择": "Apply selection",
  "语言": "Language",
  "请求失败": "Request failed",
  "未提供": "Not provided",
  "未启用": "Disabled",
  "已启用": "Enabled",
  "流量未提供": "Traffic data unavailable",
  "流量不足": "Low traffic balance",
  "已到期": "Expired",
  "拉取或检测异常，使用缓存": "Fetch or check failed; using cache",
  "拖动调整顺序，或使用方向键": "Drag to reorder, or use arrow keys",
  "拖动排序，或聚焦后使用方向键": "Drag to reorder, or focus and use arrow keys",
  "访问官网": "Visit website",
  "更新订阅": "Update subscription",
  "检查节点": "Check nodes",
  "在新标签页打开官网": "Open website in a new tab",
  "未设置官网": "No website configured",
  "添加机场": "Add provider",
  "机场顺序已保存": "Provider order saved",
  "放弃尚未保存的修改？": "Discard unsaved changes?",
  "正在保存，请稍候": "Saving, please wait",
  "已保存，后台将更新订阅。": "Saved. The subscription will update in the background.",
  "订阅地址必须使用 HTTPS": "The subscription URL must use HTTPS",
  "官网必须使用 HTTP/HTTPS，且不能包含账号密码": "The website must use HTTP/HTTPS and must not contain credentials",
  "移除此机场？缓存节点将不再包含于分享订阅。": "Remove this provider? Its cached nodes will no longer be included in the shared subscription.",
  "● 后台更新中": "● Updating in background",
  "● 后台待机": "● Background worker idle",
  " · 使用缓存": " · Using cache",
  "分流规则等待更新": "Waiting for routing rules to update",
  " · 下载失败，完整订阅暂不可用": " · Download failed; full subscription temporarily unavailable",
  "间隔至少为 1 分钟": "Intervals must be at least 1 minute",
  "已复制": "Copied",
  "请选中链接手动复制": "Select the URL and copy it manually",
  "所有节点归入“其他国家”": "All nodes go into the “其他国家” group",
  "任务已提交，后台完成后自动更新。": "Task submitted. Results update automatically when it completes.",
  "（未启用）": " (disabled)",
  "可用": "Healthy",
  "检测失败": "Check failed",
  "未检测": "Not checked",
  "已排除": "Excluded",
  "未排除": "Not excluded",
  "延迟未记录": "Latency not recorded",
  "机场未启用": "Provider disabled",
  "参与发布": "Published",
  "节点详情": "Node details",
  "恢复": "Restore",
  "规则排除": "Excluded by rule",
  "排除": "Exclude",
  "没有匹配的节点": "No matching nodes",
  "暂无缓存节点，请先更新机场订阅": "No cached nodes. Update provider subscriptions first",
  "至少选择地区、协议或填写名称关键词": "Select a region, protocol or enter a name keyword",
  "排除不可用节点": "Exclude unhealthy nodes",
  "按服务器最近检测结果排除检测失败节点，未检测节点保留；恢复可用后自动恢复发布。": "Exclude nodes that failed the server's last check. Keep unchecked nodes and automatically republish nodes that recover.",
  "删除规则": "Delete rule",
  "该规则已存在": "This rule already exists",
  "状态读取失败，请刷新页面": "Could not load status. Please refresh the page",
  "请求来源无效": "Invalid request origin",
  "配置已被其他页面修改，请刷新页面后重试": "Configuration changed in another page. Refresh and try again",
  "请稍后再试": "Please try again later",
  "后台已有任务，请等待完成后再试": "A background task is running. Wait for it to finish and try again",
  "配置无效：请检查机场 ID、HTTPS 地址、代理格式和时间间隔": "Invalid configuration: check provider IDs, HTTPS URLs, proxy formats and intervals",
  "剩余 {remaining} / {total}": "Remaining {remaining} / {total}",
  "到期日 · {date}": "Expires · {date}",
  "总节点 {total} · 已发布 {published} · 可用 {healthy}": "Nodes {total} · Published {published} · Healthy {healthy}",
  "信息更新 · {date}": "Info updated · {date}",
  "机场提供的数据：剩余 {remaining}；到期日 {date}": "Provider data: remaining {remaining}; expires {date}",
  "● 更新失败 · {error} · {date}": "● Update failed · {error} · {date}",
  "最近成功：{success}；最近失败：{failure}": "Last success: {success}; last failure: {failure}",
  "分流规则更新：{date}": "Routing rules updated: {date}",
  "已选择 {count} 个地区，其余归入“其他国家”": "{count} regions selected; remaining nodes go into “其他国家”",
  "{label}（{count} 项）": "{label} ({count} selected)",
  "显示 {shown} / {total} 个节点 · 已排除 {excluded} 个": "Showing {shown} / {total} nodes · {excluded} excluded",
  "排除当前筛选结果（{count}）": "Exclude filtered nodes ({count})",
  "恢复当前筛选结果（{count}）": "Restore filtered nodes ({count})",
  "已排除 {count} 个节点，原始缓存保留。": "Excluded {count} nodes. Original cache preserved.",
  "已解除 {count} 个节点的手动排除，持续规则仍然生效。": "Removed manual exclusions for {count} nodes. Persistent rules still apply.",
  "当前匹配 {count} 个节点": "Currently matches {count} nodes",
  "名称包含「{keyword}」": "Name contains “{keyword}”",
  "启用规则：{rule}": "Enable rule: {rule}",
  "🌐 其他地区": "🌐 Other regions",
  "简体中文": "简体中文"
};
  function resolveLocale(saved, languages = []) {
    if (saved === 'zh-CN' || saved === 'en') return saved;
    for (const language of languages) {
      if (/^zh(?:-|$)/i.test(language)) return 'zh-CN';
      if (/^en(?:-|$)/i.test(language)) return 'en';
    }
    return 'zh-CN';
  }
  let saved;
  try { saved = localStorage.getItem('panel-language'); } catch {}
  let locale = resolveLocale(saved, navigator.languages || [navigator.language]);
  function t(key, values = {}) {
    const message = locale === 'en' ? en[key] ?? key : key;
    return message.replace(/\{(\w+)\}/g, (match, name) => Object.hasOwn(values, name) ? String(values[name]) : match);
  }
  function setLocale(value) {
    locale = resolveLocale(value);
    try { localStorage.setItem('panel-language', locale); } catch {}
  }
  function translateDOM(root) {
    if (root === document) document.documentElement.lang = locale;
    for (const el of root.querySelectorAll('[data-i18n]')) el.textContent = t(el.dataset.i18n);
    for (const attr of ['aria-label', 'title', 'placeholder']) {
      for (const el of root.querySelectorAll('[data-i18n-' + attr + ']')) el.setAttribute(attr, t(el.getAttribute('data-i18n-' + attr)));
    }
  }
  function country(label) {
    if (!label || locale === 'zh-CN') return label;
    const flag = [...label.split(' ')[0]];
    if (flag.length === 2 && flag.every(c => c.codePointAt(0) >= 0x1f1e6 && c.codePointAt(0) <= 0x1f1ff)) {
      const code = flag.map(c => String.fromCharCode(c.codePointAt(0) - 0x1f1e6 + 65)).join('');
      try { return flag.join('') + ' ' + new Intl.DisplayNames(['en'], {type:'region', style:'short'}).of(code); } catch {}
    }
    return t(label);
  }
  return {t, resolveLocale, setLocale, translateDOM, country, get locale() { return locale; }};
})();
