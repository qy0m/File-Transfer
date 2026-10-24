export type DroppedFile = {
  file: File;
  path: string;
};

export async function collectDroppedFiles(
  transfer: DataTransfer
): Promise<DroppedFile[]> {
  // Capture entries while the drop event can still access them.
  const items = Array.from(transfer.items).filter(
    item => item.kind === "file"
  );

  const roots = items.map(item => {
    const entry = typeof item.webkitGetAsEntry === "function"
      ? item.webkitGetAsEntry()
      : null;

    return {
      entry,
      file: entry ? null : item.getAsFile()
    };
  });

  if (!roots.length) {
    for (const file of Array.from(transfer.files)) {
      roots.push({ entry: null, file });
    }
  }

  const files: DroppedFile[] = [];
  const seen = new Set<string>();

  let total = 0;
  let visited = 0;

  function add(file: File, path: string): void {
    if (files.length >= 25) {
      throw new Error("Choose no more than 25 files.");
    }

    if (total + file.size > 5_000_000_000) {
      throw new Error("The combined size must be 5 GB or less.");
    }

    if (seen.has(path)) {
      throw new Error(
        "Two dropped files have the same folder path."
      );
    }

    seen.add(path);
    total += file.size;

    files.push({ file, path });
  }

  async function walk(
    entry: FileSystemEntry,
    parent = "",
    depth = 0
  ): Promise<void> {
    visited++;

    if (visited > 5000 || depth > 64) {
      throw new Error(
        "This folder has too many entries. Choose a smaller folder."
      );
    }

    const path = parent
      ? `${parent}/${entry.name}`
      : entry.name;

    if (new TextEncoder().encode(path).length > 1024) {
      throw new Error("A folder path is too long.");
    }

    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) => {
        (entry as FileSystemFileEntry).file(resolve, reject);
      });

      add(file, path);
      return;
    }

    if (!entry.isDirectory) {
      throw new Error("Could not read a dropped item.");
    }

    const reader =
      (entry as FileSystemDirectoryEntry).createReader();

    while (true) {
      const children = await new Promise<FileSystemEntry[]>(
        (resolve, reject) => {
          reader.readEntries(resolve, reject);
        }
      );

      if (!children.length) break;

      for (const child of children) {
        await walk(child, path, depth + 1);
      }
    }
  }

  for (const root of roots) {
    if (root.entry) {
      await walk(root.entry);
    } else if (root.file) {
      add(
        root.file,
        root.file.webkitRelativePath || root.file.name
      );
    } else {
      throw new Error(
        "Could not read the drop. Use Browse files or Browse folder."
      );
    }
  }

  if (!files.length) {
    throw new Error(
      "No files found. Empty folders are not uploaded."
    );
  }

  return files;
}