import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// Format conversions only: preserve the checked-in uwork artwork without redrawing it.
const root = resolve(fileURLToPath(new URL('..', import.meta.url)))
const source = join(root, 'desktop-workbench/build/icon-mac-source.png')
const temp = mkdtempSync(join(tmpdir(), 'yuncontrol-brand-'))
try {
  // Modern ICNS slots contain PNG data; write the documented container directly.
  const chunks = [['icp4', 16], ['icp5', 32], ['icp6', 64], ['ic07', 128], ['ic08', 256], ['ic09', 512], ['ic10', 1024]].map(([type, size]) => {
    const file = join(temp, `mac-${size}.png`)
    execFileSync('sips', ['-z', String(size), String(size), source, '--out', file], { stdio: 'pipe' })
    const png = readFileSync(file)
    const header = Buffer.alloc(8)
    header.write(type, 0, 4, 'ascii')
    header.writeUInt32BE(8 + png.length, 4)
    return Buffer.concat([header, png])
  })
  const icnsHeader = Buffer.alloc(8)
  icnsHeader.write('icns', 0, 4, 'ascii')
  icnsHeader.writeUInt32BE(8 + chunks.reduce((total, chunk) => total + chunk.length, 0), 4)
  writeFileSync(join(root, 'desktop-workbench/build/icon.icns'), Buffer.concat([icnsHeader, ...chunks]))
  const sizes = [16, 24, 32, 48, 64, 128, 256]
  const images = sizes.map(size => {
    const file = join(temp, `windows-${size}.png`)
    execFileSync('sips', ['-z', String(size), String(size), source, '--out', file], { stdio: 'pipe' })
    return readFileSync(file)
  })
  const header = Buffer.alloc(6 + 16 * sizes.length)
  header.writeUInt16LE(1, 2)
  header.writeUInt16LE(sizes.length, 4)
  let offset = header.length
  images.forEach((data, index) => {
    const entry = 6 + 16 * index
    header[entry] = header[entry + 1] = sizes[index] === 256 ? 0 : sizes[index]
    header.writeUInt16LE(1, entry + 4)
    header.writeUInt16LE(32, entry + 6)
    header.writeUInt32LE(data.length, entry + 8)
    header.writeUInt32LE(offset, entry + 12)
    offset += data.length
  })
  writeFileSync(join(root, 'desktop-workbench/build/icon.ico'), Buffer.concat([header, ...images]))
} finally {
  rmSync(temp, { recursive: true, force: true })
}
