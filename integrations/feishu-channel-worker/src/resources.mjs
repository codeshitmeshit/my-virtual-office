import { randomUUID } from 'node:crypto';
import { chmod, lstat, mkdir, realpath, stat, unlink } from 'node:fs/promises';
import { basename, extname, join, resolve, sep } from 'node:path';

export const MAX_RESOURCE_BYTES = 50 * 1024 * 1024;

const MIME_EXTENSIONS = {
  'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif', 'image/webp': '.webp',
  'application/pdf': '.pdf', 'text/plain': '.txt', 'application/zip': '.zip',
};

function safeDisplayName(value) {
  const name = basename(String(value || '')).replace(/[^\p{L}\p{N}._-]+/gu, '_').slice(0, 100);
  return name && name !== '.' && name !== '..' ? name : 'resource';
}

export class ResourceStore {
  constructor(root, { maxBytes = MAX_RESOURCE_BYTES } = {}) {
    this.root = resolve(root);
    this.canonicalRoot = '';
    this.maxBytes = maxBytes;
  }

  async initialize() {
    await mkdir(this.root, { recursive: true, mode: 0o700 });
    const info = await lstat(this.root);
    if (info.isSymbolicLink() || !info.isDirectory()) throw Object.assign(new Error('attachment root must be a real directory'), { code: 'unsafe_resource_path' });
    this.canonicalRoot = await realpath(this.root);
    await chmod(this.root, 0o700);
  }

  async download(channel, { messageId, fileKey, resourceType, displayName = '' }) {
    if (!['image', 'file'].includes(resourceType)) throw Object.assign(new Error('unsupported resource type'), { code: 'unsupported_resource_type' });
    await this.initialize();
    const base = safeDisplayName(displayName);
    const requestedExtension = extname(base).slice(0, 12);
    const stem = base.slice(0, Math.max(1, base.length - requestedExtension.length));
    const generated = `${stem}-${randomUUID()}${requestedExtension}`;
    const path = resolve(join(this.canonicalRoot, generated));
    if (!path.startsWith(`${this.canonicalRoot}${sep}`)) throw Object.assign(new Error('unsafe resource destination'), { code: 'unsafe_resource_path' });
    try {
      const result = await channel.downloadResourceToFile(messageId, fileKey, resourceType, path);
      const size = Number(result?.bytesWritten ?? (await stat(path)).size);
      if (size > this.maxBytes) throw Object.assign(new Error(`resource exceeds ${this.maxBytes} bytes`), { code: 'resource_too_large' });
      const contentType = String(result?.contentType || (resourceType === 'image' ? 'image/png' : 'application/octet-stream'));
      let finalPath = path;
      if (!requestedExtension && MIME_EXTENSIONS[contentType]) {
        const withExtension = `${path}${MIME_EXTENSIONS[contentType]}`;
        const { rename } = await import('node:fs/promises');
        await rename(path, withExtension);
        finalPath = withExtension;
      }
      await chmod(finalPath, 0o600);
      return { ok: true, status: 'downloaded', messageId, fileKey, resourceType, name: basename(finalPath), path: finalPath, contentType, mimeType: contentType, size };
    } catch (error) {
      await unlink(path).catch(() => {});
      for (const extension of Object.values(MIME_EXTENSIONS)) await unlink(`${path}${extension}`).catch(() => {});
      throw error;
    }
  }
}
