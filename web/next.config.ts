import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The floating dev badge sat over the filters panel and the status bar.
  devIndicators: false,
  images: {
    // Next 16 requires an allowlist. 75 for pictures; 85 for the hero photograph.
    qualities: [75, 85],
    deviceSizes: [640, 828, 1080, 1440, 1920, 2400],
    imageSizes: [96, 160, 256, 384, 480],
  },
};

export default nextConfig;
