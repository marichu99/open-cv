import * as React from "react";
import { cn } from "@/lib/utils";

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value: number;
}

const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(({ className, value, ...props }, ref) => (
  <div
    ref={ref}
    role="progressbar"
    aria-valuenow={value}
    aria-valuemin={0}
    aria-valuemax={100}
    className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}
    {...props}
  >
    <div
      className="h-full rounded-full bg-primary transition-[width] duration-500"
      style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
    />
  </div>
));
Progress.displayName = "Progress";

export { Progress };
