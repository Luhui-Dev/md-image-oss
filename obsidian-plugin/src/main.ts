import {
  Editor,
  MarkdownFileInfo,
  MarkdownView,
  Menu,
  Notice,
  Plugin,
  TFile,
} from "obsidian";
import {
  DEFAULT_SETTINGS,
  MdImageOssSettingTab,
  MdImageOssSettings,
  buildUploaderConfig,
  validateConfig,
} from "./settings";
import { Uploader } from "./core/uploader";
import {
  applyResults,
  PipelineResult,
  ScannedItem,
  scanNote,
  uploadSelected,
} from "./core/pipeline";
import { rewriteRef } from "./core/rewriter";
import { ProgressNotice } from "./ui/ProgressNotice";
import { FailureModal } from "./ui/FailureModal";
import { ImageListModal } from "./ui/ImageListModal";
import { t } from "./i18n";

export default class MdImageOssPlugin extends Plugin {
  settings!: MdImageOssSettings;

  async onload(): Promise<void> {
    await this.loadSettings();

    this.addSettingTab(new MdImageOssSettingTab(this.app, this));
    const T = t();

    this.addCommand({
      id: "upload-all-in-current-note",
      name: T.cmd.uploadAll,
      checkCallback: (checking) => {
        const view = this.app.workspace.getActiveViewOfType(MarkdownView);
        if (!view || !view.file) return false;
        if (checking) return true;
        void this.runUploadAll(view);
        return true;
      },
    });

    this.addCommand({
      id: "open-image-manager",
      name: T.cmd.openManager,
      checkCallback: (checking) => {
        const view = this.app.workspace.getActiveViewOfType(MarkdownView);
        if (!view || !view.file) return false;
        if (checking) return true;
        void this.runImageManager(view);
        return true;
      },
    });

    // File menu (More options on the note tab)
    this.registerEvent(
      this.app.workspace.on("file-menu", (menu: Menu, file: unknown) => {
        if (!(file instanceof TFile) || !this.isSupported(file)) return;
        const M = t().menu;
        menu.addItem((i) =>
          i.setTitle(M.uploadAll)
            .setIcon("image-up")
            .onClick(() => void this.runUploadAllForFile(file)),
        );
        menu.addItem((i) =>
          i.setTitle(M.openManager)
            .setIcon("images")
            .onClick(() => void this.runImageManagerForFile(file)),
        );
      }),
    );

    // Editor context menu
    this.registerEvent(
      this.app.workspace.on("editor-menu", (menu: Menu, _editor: Editor, info: MarkdownView | MarkdownFileInfo) => {
        if (!(info instanceof MarkdownView)) return;
        if (!info.file || !this.isSupported(info.file)) return;
        const view = info;
        const M = t().menu;
        menu.addItem((i) =>
          i.setTitle(M.uploadAll)
            .setIcon("image-up")
            .onClick(() => void this.runUploadAll(view)),
        );
        menu.addItem((i) =>
          i.setTitle(M.openManager)
            .setIcon("images")
            .onClick(() => void this.runImageManager(view)),
        );
      }),
    );
  }

  async loadSettings(): Promise<void> {
    const data = (await this.loadData()) as Partial<MdImageOssSettings> | null;
    this.settings = Object.assign({}, DEFAULT_SETTINGS, data ?? {});
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  // -- commands --------------------------------------------------------------

  private isSupported(file: TFile): boolean {
    const e = file.extension.toLowerCase();
    return e === "md" || e === "mdx" || e === "markdown" || e === "html" || e === "htm";
  }

  private requireConfigured(): Uploader | null {
    const err = validateConfig(this.settings);
    if (err) {
      new Notice(t().notice.configMissing(err), 6000);
      return null;
    }
    return new Uploader(buildUploaderConfig(this.settings));
  }

  private async runUploadAll(view: MarkdownView): Promise<void> {
    const file = view.file;
    if (!file) return;
    const uploader = this.requireConfigured();
    if (!uploader) return;
    const content = view.editor.getValue();
    const items = scanNote(this.app, file, content, { obsidian: true });
    if (items.length === 0) { new Notice(t().notice.noImages); return; }
    await this.runPipeline(view, uploader, items);
  }

  private async runUploadAllForFile(file: TFile): Promise<void> {
    const uploader = this.requireConfigured();
    if (!uploader) return;
    const content = await this.app.vault.read(file);
    const items = scanNote(this.app, file, content, { obsidian: true });
    if (items.length === 0) { new Notice(t().notice.noImages); return; }
    await this.runPipelineForFile(file, uploader, items);
  }

  private async runImageManager(view: MarkdownView): Promise<void> {
    const file = view.file;
    if (!file) return;
    const uploader = this.requireConfigured();
    if (!uploader) return;
    const content = view.editor.getValue();
    const items = scanNote(this.app, file, content, { obsidian: true });
    if (items.length === 0) { new Notice(t().notice.noImages); return; }
    const sizes = await this.collectSizes(items);
    const modal = new ImageListModal(this.app, items, sizes);
    const result = await modal.open();
    if (!result.confirmed || result.selected.length === 0) return;
    await this.runPipeline(view, uploader, result.selected);
  }

  private async runImageManagerForFile(file: TFile): Promise<void> {
    const uploader = this.requireConfigured();
    if (!uploader) return;
    const content = await this.app.vault.read(file);
    const items = scanNote(this.app, file, content, { obsidian: true });
    if (items.length === 0) { new Notice(t().notice.noImages); return; }
    const sizes = await this.collectSizes(items);
    const modal = new ImageListModal(this.app, items, sizes);
    const result = await modal.open();
    if (!result.confirmed || result.selected.length === 0) return;
    await this.runPipelineForFile(file, uploader, result.selected);
  }

  private async collectSizes(items: ScannedItem[]): Promise<Map<ScannedItem, number>> {
    const sizes = new Map<ScannedItem, number>();
    await Promise.all(items.map(async (it) => {
      if (it.resolved.status === "local") {
        try {
          const stat = await this.app.vault.adapter.stat(it.resolved.file.path);
          if (stat && typeof stat.size === "number") sizes.set(it, stat.size);
        } catch { /* ignore */ }
      }
    }));
    return sizes;
  }

  private async runPipeline(
    view: MarkdownView,
    uploader: Uploader,
    items: ScannedItem[],
  ): Promise<void> {
    const progress = new ProgressNotice(t().progress.title);
    const ac = new AbortController();
    let result: PipelineResult;
    try {
      result = await uploadSelected(
        this.app,
        uploader,
        items,
        {
          compress: this.settings.compress,
          quality: this.settings.quality,
          processRemote: this.settings.processRemote,
          obsidian: true,
          concurrency: this.settings.concurrency,
          signal: ac.signal,
        },
        (done, total, current) => progress.update(done, total, current),
      );
    } catch (e) {
      progress.hide();
      const msg = e instanceof Error ? e.message : String(e);
      new Notice(t().notice.pipelineError(msg), 8000);
      return;
    }

    // Apply changes via editor.transaction to preserve undo + cursor.
    const editor = view.editor;
    const liveText = editor.getValue();
    const applicable = result.results.filter((r) => r.status === "uploaded" && r.newUrl);
    // Sort ascending; editor.transaction wants ascending changes.
    applicable.sort((a, b) => a.ref.from - b.ref.from);

    const changes: { from: { line: number; ch: number }; to: { line: number; ch: number }; text: string }[] = [];
    let drift = 0;
    for (const r of applicable) {
      const sliceLive = liveText.slice(r.ref.from, r.ref.to);
      if (sliceLive !== r.ref.originalText) { drift++; continue; }
      const replacement = rewriteRef(r.ref, r.newUrl!);
      changes.push({
        from: editor.offsetToPos(r.ref.from),
        to: editor.offsetToPos(r.ref.to),
        text: replacement,
      });
    }
    if (changes.length > 0) {
      editor.transaction({ changes });
    }

    this.reportSummary(progress, result, drift);
  }

  private async runPipelineForFile(
    file: TFile,
    uploader: Uploader,
    items: ScannedItem[],
  ): Promise<void> {
    const progress = new ProgressNotice(t().progress.title);
    const ac = new AbortController();
    const result = await uploadSelected(
      this.app,
      uploader,
      items,
      {
        compress: this.settings.compress,
        quality: this.settings.quality,
        processRemote: this.settings.processRemote,
        obsidian: true,
        concurrency: this.settings.concurrency,
        signal: ac.signal,
      },
      (done, total, current) => progress.update(done, total, current),
    );

    // Use vault.process for atomic read-modify-write on non-active files.
    let drift = 0;
    await this.app.vault.process(file, (current: string) => {
      const applied = applyResults(current, result.results);
      drift = applied.driftedCount;
      return applied.content;
    });
    this.reportSummary(progress, result, drift);
  }

  private reportSummary(
    progress: ProgressNotice,
    result: PipelineResult,
    drift: number,
  ): void {
    const { stats } = result;
    progress.finish(t().progress.done(stats.found, stats.uploaded, stats.skipped, stats.failed, drift));
    const failures = result.results.filter((r) => r.status === "failed");
    if (failures.length > 0) new FailureModal(this.app, failures).open();
  }
}
