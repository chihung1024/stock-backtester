/** @type {import('next').NextConfig} */
const nextConfig = {
  // 這個檔案雖然是空的，但它的存在會告訴 Vercel 和 Next.js
  // 使用標準的伺服器模式來運行您的應用程式，
  // 而不是將其匯出為純靜態網站。
  //
  // 這樣一來，您在 /app/api/ 路徑下的 API 路由就能被正確識別和執行，
  // 從而解決 404 NOT_FOUND 的錯誤。
};

export default nextConfig;
