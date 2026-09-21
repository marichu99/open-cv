import * as React from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Command, CommandInput, CommandList, CommandEmpty, CommandItem } from "@/components/ui/command";

/**
 * A searchable dropdown — same trigger/value contract as `Select`
 * (string `value` + `onChange`), but with a filter box up front instead of
 * a plain scrollable list. Reach for this over `Select` whenever the list
 * is long/open-ended enough that scanning it isn't realistic (registered
 * aspirants, campaign managers, polling stations, ...).
 */
export function Combobox<T>({
  id,
  items,
  value,
  onChange,
  getId,
  getSearchText,
  renderTrigger,
  renderItem,
  placeholder = "Select…",
  searchPlaceholder = "Search…",
  emptyText = "No matches.",
  disabled,
  triggerClassName,
}: {
  id?: string;
  items: T[];
  value: string | null;
  onChange: (id: string) => void;
  getId: (item: T) => string;
  getSearchText: (item: T) => string;
  renderTrigger?: (item: T) => React.ReactNode;
  renderItem?: (item: T) => React.ReactNode;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  disabled?: boolean;
  triggerClassName?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const selected = items.find((item) => getId(item) === value) ?? null;
  const isDisabled = disabled || items.length === 0;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          disabled={isDisabled}
          className={cn(
            "flex h-10 w-full items-center justify-between rounded-md border border-input bg-card px-3 py-2 text-sm",
            "focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
            selected && "h-auto min-h-10 py-2",
            triggerClassName
          )}
        >
          {selected ? (
            renderTrigger ? renderTrigger(selected) : <span>{getSearchText(selected)}</span>
          ) : (
            <span className="text-muted-foreground">{placeholder}</span>
          )}
          <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="p-0">
        <Command>
          <CommandInput placeholder={searchPlaceholder} />
          <CommandList>
            <CommandEmpty>{emptyText}</CommandEmpty>
            {items.map((item) => {
              const itemId = getId(item);
              return (
                <CommandItem
                  key={itemId}
                  value={getSearchText(item)}
                  onSelect={() => {
                    onChange(itemId);
                    setOpen(false);
                  }}
                  className="gap-2 pl-2"
                >
                  <Check className={cn("h-3.5 w-3.5 shrink-0", itemId === value ? "opacity-100" : "opacity-0")} />
                  <span className="min-w-0 flex-1">{renderItem ? renderItem(item) : getSearchText(item)}</span>
                </CommandItem>
              );
            })}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
