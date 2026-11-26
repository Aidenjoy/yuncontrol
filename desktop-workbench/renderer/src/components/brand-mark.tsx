import { cn } from "@/lib/utils"

/** Cloud brand mark copied from uwork; decorative when accompanied by the product name. */
export function BrandMark({
  className,
  label,
}: {
  className?: string
  label?: string
}) {
  return (
    <img
      src="/brand/cloud-logo.svg"
      alt={label ?? ""}
      aria-hidden={label ? undefined : true}
      className={cn("inline-block size-6 shrink-0 align-middle", className)}
    />
  )
}
