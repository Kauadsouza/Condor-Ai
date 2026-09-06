import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Condor AI Cloud",
    short_name: "Condor AI",
    description: "A mesma mente do Condor no celular e no PC.",
    start_url: "/",
    display: "standalone",
    background_color: "#02050b",
    theme_color: "#02050b",
    icons: [{ src: "/condor.svg", sizes: "any", type: "image/svg+xml", purpose: "maskable" }],
  };
}
