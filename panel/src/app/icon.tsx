import { ImageResponse } from "next/og";

export const size = { width: 64, height: 64 };
export const contentType = "image/png";

// Favicon: the same "RF" mark the sidebar renders, generated at build time.
export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#16212b",
          color: "#ffffff",
          borderRadius: 12,
          fontSize: 30,
          fontWeight: 700,
          letterSpacing: -1,
        }}
      >
        RF
      </div>
    ),
    size,
  );
}
