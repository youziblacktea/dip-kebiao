/* DIPLOMA 课表 —— Service Worker（离线外壳）
   2026-10-13 由 tools/build_timetable.py 在构建时替换成数据快照日期，
   这样每次重新构建都会换一个缓存名，旧缓存自动清理。 */
const CACHE = 'diploma-timetable-2026-10-13';

const ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/maskable-512.png',
  './icons/apple-touch-icon.png',
  './data/timetable.json'
];

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await Promise.all(ASSETS.map(async url => {
      try { await cache.add(url); } catch (e) { /* 个别文件拉不到不影响整体安装 */ }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

/* 判断一个响应是不是“我们自己的课表页面”。
   托管平台在暂停/欠费/502 时会返回 HTML 错误页，而状态码常常仍是 200，
   所以必须靠内容特征识别，避免错误页被写进缓存、顶掉本地课表。 */
async function looksLikeOurApp(res) {
  try {
    const type = res.headers.get('content-type') || '';
    if (!type.includes('text/html')) return false;
    const text = await res.text();
    return text.includes('id="nextcard"') && text.includes('DIPLOMA 课表');
  } catch (e) {
    return false;
  }
}

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;

  let url;
  try { url = new URL(req.url); } catch (e) { return; }
  if (url.origin !== self.location.origin) return;   // 只用本应用自己的资源

  // 页面导航：优先网络（拿到最新课表），拿不到或拿到的不是本应用页面时，回落缓存
  if (req.mode === 'navigate') {
    event.respondWith((async () => {
      const cached = (await caches.match('./index.html')) || (await caches.match('./'));
      let fresh = null;
      try {
        fresh = await Promise.race([
          fetch(req),
          new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 3000))
        ]);
      } catch (e) { fresh = null; }

      // 关键加固：托管平台可能返回“本网站已暂停使用”“502 Bad Gateway”之类的 HTML 页面，
      // 状态码往往还是 200。这类页面绝不能写进缓存，也绝不能顶掉本地已有的课表。
      if (fresh && fresh.ok && await looksLikeOurApp(fresh.clone())) {
        const cache = await caches.open(CACHE);
        cache.put('./index.html', fresh.clone()).catch(() => {});
        return fresh;
      }
      return cached || fresh || Response.error();
    })());
    return;
  }

  // 静态资源：缓存优先，后台顺手更新
  event.respondWith((async () => {
    const cached = await caches.match(req, { ignoreSearch: true });
    const network = fetch(req).then(res => {
      if (res && res.ok) caches.open(CACHE).then(c => c.put(req, res.clone())).catch(() => {});
      return res;
    }).catch(() => null);
    return cached || (await network) || Response.error();
  })());
});
