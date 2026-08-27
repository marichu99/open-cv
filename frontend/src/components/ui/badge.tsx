import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold before:h-1.5 before:w-1.5 before:rounded-full before:bg-current",
  {
    variants: {
      variant: {
        default: "bg-accent text-accent-foreground",
        success: "bg-accent text-accent-foreground",
        warning: "bg-warning/15 text-warning",
        destructive: "bg-destructive/15 text-destructive",
        neutral: "border border-border bg-muted text-muted-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
