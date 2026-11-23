# 新闻超链接 播客订阅源

把中国之声《新闻超链接》（每天 21:00–22:00）做成一个播客 RSS。
**只存链接，不存音频文件**，App 点开直接在线播放。

## 文件

| 文件 | 作用 |
|---|---|
| `make_feed.py` | 抓取 + 校验 + 生成 `feed.xml` |
| `episodes.json` | 已收录的期数（增量基础，别删） |
| `feed.xml` | 生成的订阅文件，App 订阅这个地址 |
| `.github/workflows/feed.yml` | 每天北京时间 22:30 自动跑 |

## 订阅地址

仓库启用 GitHub Pages 后：

```
https://你的用户名.github.io/仓库名/feed.xml
```

在 AntennaPod 里「添加播客 → 输入 RSS 地址」粘贴即可。

没开 Pages 的话，这个地址也能用（但加载稍慢）：

```
https://raw.githubusercontent.com/你的用户名/仓库名/main/feed.xml
```

## 数据来源

云听官方节目单接口：

```
https://ytmsout.radio.cn/web/appProgram/listByDate?date=YYYY-MM-DD&broadcastId=639
```

- `broadcastId=639` 是中国之声
- 返回当天全部节目，取 `programName == "新闻超链接"`
- 音频地址取 `playUrlHigh`，两种格式：
  - `https://ytrecordbroadcast.radio.cn/echo/2/xxxx.m4a?e=0&ps=1&r=1`
  - `https://ytmedia.radio.cn/file/202611/12/23/xxxh.mp3`
- **都不带过期签名，可长期使用**

## 首次使用

1. 新建仓库（public），把这些文件原样上传
2. Actions 页面 → 选中「更新新闻超链接 RSS」→ Run workflow → `days` 填 `400`，可补齐过去一年
3. Settings → Pages → Source 选 `Deploy from a branch` → 分支 `main`、目录 `/ (root)` → Save
4. 等 1–2 分钟，用 `https://用户名.github.io/仓库名/feed.xml` 订阅

## 日常

不用管。每天 22:30 自动抓当天新一期，写进 `feed.xml` 并提交。

- 停跑一天，第二天会一次补上两天（脚本按日期扫最近 N 天，已收录的自动跳过）
- 某期音频取不到就跳过，不会写坏地址
- 想手动补抓：Run workflow，`days` 填要回看的天数

## 排查

| 现象 | 原因 |
|---|---|
| App 里没有新一期 | 节目还没上传到云听，次日会补 |
| 某一期点开报错 | 那期音频可能下架了，脚本下次运行会重取地址 |
| feed.xml 打不开 | Pages 没开，或分支/目录选错 |
