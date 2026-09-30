/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",          // statik build → nginx beradi (eng tez, server kerak emas)
  trailingSlash: true,
  reactStrictMode: true,
  images: { unoptimized: true },
  poweredByHeader: false,
};
export default nextConfig;
