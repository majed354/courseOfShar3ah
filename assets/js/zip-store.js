/* A small ZIP32 writer for already-compressed PDF files. No external service or library is needed. */
(function (root) {
    'use strict';

    const encoder = new TextEncoder();
    const crcTable = new Uint32Array(256);
    for (let i = 0; i < 256; i += 1) {
        let value = i;
        for (let bit = 0; bit < 8; bit += 1) {
            value = value & 1 ? (value >>> 1) ^ 0xEDB88320 : value >>> 1;
        }
        crcTable[i] = value >>> 0;
    }

    function crc32(bytes) {
        let crc = 0xFFFFFFFF;
        for (const byte of bytes) crc = (crc >>> 8) ^ crcTable[(crc ^ byte) & 255];
        return (crc ^ 0xFFFFFFFF) >>> 0;
    }

    function dosTimestamp(date) {
        const year = Math.max(1980, Math.min(2107, date.getFullYear()));
        return {
            time: (date.getHours() << 11) | (date.getMinutes() << 5) | (date.getSeconds() >> 1),
            day: ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate()
        };
    }

    class ZipStore {
        constructor(sink) {
            this.sink = sink;
            this.offset = 0;
            this.entries = [];
            this.names = new Set();
            this.closed = false;
        }

        async write(bytes) {
            if (this.offset + bytes.length > 0xFFFFFFFF) {
                throw new Error('حجم الحزمة يتجاوز الحد المدعوم 4 جيجابايت.');
            }
            await this.sink.write(bytes);
            this.offset += bytes.length;
        }

        async add(path, content) {
            if (this.closed) throw new Error('أُغلقت الحزمة.');
            if (!path || path.startsWith('/') || path.split('/').includes('..') || this.names.has(path)) {
                throw new Error(`مسار ملف غير صالح أو مكرر: ${path}`);
            }
            const name = encoder.encode(path);
            const bytes = typeof content === 'string' ? encoder.encode(content) : content;
            if (!(bytes instanceof Uint8Array) || name.length > 0xFFFF || bytes.length > 0xFFFFFFFF) {
                throw new Error(`ملف غير صالح للحزمة: ${path}`);
            }
            const crc = crc32(bytes);
            const stamp = dosTimestamp(new Date());
            const header = new Uint8Array(30 + name.length);
            const view = new DataView(header.buffer);
            view.setUint32(0, 0x04034B50, true);
            view.setUint16(4, 20, true);
            view.setUint16(6, 0x0800, true); // UTF-8 names
            view.setUint16(10, stamp.time, true);
            view.setUint16(12, stamp.day, true);
            view.setUint32(14, crc, true);
            view.setUint32(18, bytes.length, true);
            view.setUint32(22, bytes.length, true);
            view.setUint16(26, name.length, true);
            header.set(name, 30);
            this.entries.push({ name, crc, size: bytes.length, offset: this.offset, stamp });
            this.names.add(path);
            await this.write(header);
            await this.write(bytes);
        }

        async close() {
            if (this.closed) throw new Error('أُغلقت الحزمة.');
            if (this.entries.length > 0xFFFF) throw new Error('عدد ملفات الحزمة يتجاوز الحد المدعوم.');
            const centralOffset = this.offset;
            for (const entry of this.entries) {
                const header = new Uint8Array(46 + entry.name.length);
                const view = new DataView(header.buffer);
                view.setUint32(0, 0x02014B50, true);
                view.setUint16(4, 20, true);
                view.setUint16(6, 20, true);
                view.setUint16(8, 0x0800, true);
                view.setUint16(12, entry.stamp.time, true);
                view.setUint16(14, entry.stamp.day, true);
                view.setUint32(16, entry.crc, true);
                view.setUint32(20, entry.size, true);
                view.setUint32(24, entry.size, true);
                view.setUint16(28, entry.name.length, true);
                view.setUint32(42, entry.offset, true);
                header.set(entry.name, 46);
                await this.write(header);
            }
            const centralSize = this.offset - centralOffset;
            const end = new Uint8Array(22);
            const view = new DataView(end.buffer);
            view.setUint32(0, 0x06054B50, true);
            view.setUint16(8, this.entries.length, true);
            view.setUint16(10, this.entries.length, true);
            view.setUint32(12, centralSize, true);
            view.setUint32(16, centralOffset, true);
            await this.write(end);
            await this.sink.close();
            this.closed = true;
        }
    }

    root.ZipStore = ZipStore;
    if (typeof module !== 'undefined' && module.exports) module.exports = { ZipStore, crc32 };
})(typeof globalThis !== 'undefined' ? globalThis : this);
