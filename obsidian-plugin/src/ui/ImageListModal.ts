import { App, Modal, TFile } from "obsidian";
import type { ScannedItem } from "../core/pipeline";
import { t } from "../i18n";

type Filter = "all" | "local" | "pending" | "missing";

export interface ImageListModalResult {
  confirmed: boolean;
  selected: ScannedItem[];
}

export class ImageListModal extends Modal {
  private filter: Filter = "all";
  private checked = new Set<ScannedItem>();
  private resolveResult!: (r: ImageListModalResult) => void;

  constructor(
    app: App,
    private readonly items: ScannedItem[],
    private readonly sizes: Map<ScannedItem, number>,
  ) {
    super(app);
    // Default selection: every item that's "local" and not already on OSS,
    // plus remote items only if the user explicitly enabled processRemote.
    // The latter we don't know here — we just pre-check local & pending.
    for (const it of items) {
      if (it.resolved.status === "local") this.checked.add(it);
    }
  }

  open(): Promise<ImageListModalResult> {
    super.open();
    return new Promise<ImageListModalResult>((resolve) => {
      this.resolveResult = resolve;
    });
  }

  onClose(): void {
    this.contentEl.empty();
    this.resolveResult?.({ confirmed: false, selected: [] });
  }

  onOpen(): void {
    const { contentEl, modalEl } = this;
    modalEl.addClass("mdoss-modal");
    contentEl.empty();
    contentEl.createEl("h3", { text: t().modal.title(this.items.length) });
    this.renderHeader(contentEl);
    const list = contentEl.createDiv({ cls: "mdoss-list" });
    this.renderList(list);
    this.renderFooter(contentEl);
  }

  private renderHeader(parent: HTMLElement): void {
    const header = parent.createDiv({ cls: "mdoss-modal-header" });
    const M = t().modal;
    const chips: Array<[Filter, string]> = [
      ["all", M.filter_all],
      ["local", M.filter_local],
      ["pending", M.filter_pending],
      ["missing", M.filter_missing],
    ];
    for (const [key, label] of chips) {
      const chip = header.createEl("span", { cls: "mdoss-filter-chip", text: label });
      if (key === this.filter) chip.addClass("is-active");
      chip.onclick = () => {
        this.filter = key;
        this.refresh();
      };
    }
    const selectAll = header.createEl("a", {
      cls: "mdoss-select-all",
      text: M.toggleVisible,
      href: "#",
    });
    selectAll.onclick = (e) => {
      e.preventDefault();
      const visible = this.visibleItems();
      const allChecked = visible.every((it) => this.checked.has(it));
      for (const it of visible) {
        if (!this.canSelect(it)) continue;
        if (allChecked) this.checked.delete(it);
        else this.checked.add(it);
      }
      this.refresh();
    };
  }

  private renderList(parent: HTMLElement): void {
    parent.empty();
    const visible = this.visibleItems();
    if (visible.length === 0) {
      parent.createEl("div", {
        text: t().modal.noMatch,
        attr: { style: "padding:1rem;color:var(--text-muted);" },
      });
      return;
    }
    for (const item of visible) this.renderRow(parent, item);
  }

  private renderRow(parent: HTMLElement, item: ScannedItem): void {
    const row = parent.createDiv({ cls: "mdoss-row" });
    if (!this.canSelect(item)) row.setAttr("data-disabled", "true");

    // Checkbox
    const cb = row.createEl("input", { type: "checkbox" });
    cb.checked = this.checked.has(item);
    cb.disabled = !this.canSelect(item);
    cb.onchange = () => {
      if (cb.checked) this.checked.add(item);
      else this.checked.delete(item);
      this.updateFooter();
    };

    // Thumbnail
    if (item.resolved.status === "local") {
      const img = row.createEl("img", { cls: "mdoss-thumb" });
      img.src = this.app.vault.getResourcePath(item.resolved.file as TFile);
      img.loading = "lazy";
    } else {
      const ph = row.createDiv({ cls: "mdoss-thumb-placeholder" });
      ph.setText(item.resolved.status === "remote" ? "🌐" : "—");
    }

    // Name + meta
    const meta = row.createDiv({ cls: "mdoss-meta" });
    meta.createEl("div", { cls: "mdoss-name", text: item.ref.rawUrl });
    const sub = meta.createDiv({ cls: "mdoss-sub" });
    sub.createEl("span", { text: kindLabel(item) });
    const size = this.sizes.get(item);
    if (size != null) sub.createEl("span", { text: fmtSize(size) });
    if (item.ref.kind === "wikilink" && item.ref.wikiSize) {
      sub.createEl("span", { text: `${item.ref.wikiSize}` });
    }

    // Status badge
    row.createEl("span", { cls: `mdoss-badge ${badgeClass(item)}`, text: badgeLabel(item) });

    // Spacer cell already handled by grid
    row.createDiv();
  }

  private renderFooter(parent: HTMLElement): void {
    const footer = parent.createDiv({ cls: "mdoss-footer" });
    const progress = footer.createDiv({ cls: "mdoss-progress" });
    progress.createDiv({ cls: "mdoss-progress-bar" });
    const counter = footer.createEl("span", { text: "" });
    const cancel = footer.createEl("button", { text: t().modal.cancel });
    cancel.onclick = () => {
      this.resolveResult({ confirmed: false, selected: [] });
      this.close();
    };
    const go = footer.createEl("button", { text: "" });
    go.addClass("mod-cta");
    go.onclick = () => {
      const selected = Array.from(this.checked);
      this.resolveResult({ confirmed: true, selected });
      this.close();
    };
    // Stash refs for live update
    (this as unknown as { _counter: HTMLElement; _go: HTMLButtonElement }).
      _counter = counter;
    (this as unknown as { _counter: HTMLElement; _go: HTMLButtonElement }).
      _go = go;
    this.updateFooter();
  }

  private updateFooter(): void {
    const ref = this as unknown as { _counter?: HTMLElement; _go?: HTMLButtonElement };
    if (!ref._counter || !ref._go) return;
    const M = t().modal;
    const n = this.checked.size;
    ref._counter.setText(M.selected(n));
    ref._go.setText(n > 0 ? M.uploadN(n) : M.upload);
    ref._go.disabled = n === 0;
  }

  private refresh(): void {
    // Cheap re-render of header chip state + list.
    this.contentEl.empty();
    this.contentEl.createEl("h3", { text: t().modal.title(this.items.length) });
    this.renderHeader(this.contentEl);
    const list = this.contentEl.createDiv({ cls: "mdoss-list" });
    this.renderList(list);
    this.renderFooter(this.contentEl);
  }

  private visibleItems(): ScannedItem[] {
    switch (this.filter) {
      case "all": return this.items;
      case "local": return this.items.filter((it) => it.resolved.status === "local");
      case "pending":
        return this.items.filter((it) =>
          it.resolved.status === "local" || (it.resolved.status === "remote" && !isOwnUrlGuess(it)),
        );
      case "missing": return this.items.filter((it) => it.resolved.status === "missing");
    }
  }

  private canSelect(item: ScannedItem): boolean {
    return item.resolved.status === "local" || item.resolved.status === "remote";
  }
}

function kindLabel(it: { ref: { kind: string } }): string {
  const M = t().modal;
  switch (it.ref.kind) {
    case "wikilink": return M.kind_wikilink;
    case "md": return M.kind_md;
    case "html": return M.kind_html;
    default: return M.kind_ref;
  }
}

function badgeLabel(it: ScannedItem): string {
  const M = t().modal;
  switch (it.resolved.status) {
    case "local": return M.badge_local;
    case "remote": return isOwnUrlGuess(it) ? M.badge_oss : M.badge_remote;
    case "missing": return M.badge_missing;
    case "skip": return M.badge_skip;
  }
}

function badgeClass(it: ScannedItem): string {
  switch (it.resolved.status) {
    case "local": return "is-local";
    case "remote": return isOwnUrlGuess(it) ? "is-oss" : "is-remote";
    case "missing": return "is-missing";
    case "skip": return "is-remote";
  }
}

// Best-effort guess used only for display purposes (real check is done in
// pipeline against uploader.isOwnUrl).
function isOwnUrlGuess(_it: ScannedItem): boolean { return false; }

function fmtSize(n: number): string {
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return i === 0 ? `${v} ${units[i]}` : `${v.toFixed(1)} ${units[i]}`;
}
