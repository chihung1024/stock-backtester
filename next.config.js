/** @type {import('next').NextConfig} */
const nextConfig = {
  // 這個設定檔能確保 Next.js 和 Vercel 在建置您的應用程式時，
  // 使用標準的伺服器模式（Server Mode）。這對於讓 API 路由
  // (例如您在 /api/stock 的後端接口) 正常運作至關重要。
  //
  // 上一個版本的錯誤在於使用了 .mjs 副檔名，該格式適用於 ES Modules。
  // 由於您的專案 package.json 中沒有設定 "type": "module"，
  // 專案預設使用的是 CommonJS 模組系統。
  // 因此，建立 .js 檔案並使用 module.exports 語法才是適合您專案的正確作法。
};

module.exports = nextConfig;
