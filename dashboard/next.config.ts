import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // GitHub Releasesでのtarball配布（issue #110）向け。`npm install`不要で
  // `node server.js`のみで起動できる最小限のnode_modulesサブセットを
  // `.next/standalone`に出力する。`.next/static`とpublic/は別途同梱が必要
  // （dist/bin/start.sh・.github/workflows/release.yml参照）。
  output: "standalone",
};

export default nextConfig;
