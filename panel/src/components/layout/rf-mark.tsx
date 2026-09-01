import { cn } from "@/lib/utils";

// Text-only brand mark: no image asset to ship or get wrong.
export function RfMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "flex h-8 w-8 shrink-0 select-none items-center justify-center rounded bg-foreground text-xs font-bold tracking-tight text-background",
        className,
      )}
    >
      RF
    </span>
  );
}
