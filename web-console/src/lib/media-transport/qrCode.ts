export type QrCodeSvgPath = {
  path: string;
  size: number;
  quietZone: number;
  viewBoxSize: number;
};

type QrVersionSpec = {
  version: number;
  dataCodewords: number;
  ecCodewordsPerBlock: number;
  blocks: number;
  alignment: number[];
};

type QrMatrix = {
  size: number;
  modules: boolean[][];
};

const BYTE_MODE = 0b0100;
const FORMAT_MASK = 0x5412;
const FORMAT_GENERATOR = 0x537;
const VERSION_GENERATOR = 0x1f25;
const LOW_ECL_FORMAT_BITS = 0b01;
const MASK_PATTERN = 0;
const QUIET_ZONE = 4;

const VERSION_SPECS: QrVersionSpec[] = [
  { version: 1, dataCodewords: 19, ecCodewordsPerBlock: 7, blocks: 1, alignment: [] },
  { version: 2, dataCodewords: 34, ecCodewordsPerBlock: 10, blocks: 1, alignment: [6, 18] },
  { version: 3, dataCodewords: 55, ecCodewordsPerBlock: 15, blocks: 1, alignment: [6, 22] },
  { version: 4, dataCodewords: 80, ecCodewordsPerBlock: 20, blocks: 1, alignment: [6, 26] },
  { version: 5, dataCodewords: 108, ecCodewordsPerBlock: 26, blocks: 1, alignment: [6, 30] },
  { version: 6, dataCodewords: 136, ecCodewordsPerBlock: 18, blocks: 2, alignment: [6, 34] },
  { version: 7, dataCodewords: 156, ecCodewordsPerBlock: 20, blocks: 2, alignment: [6, 22, 38] },
  { version: 8, dataCodewords: 194, ecCodewordsPerBlock: 24, blocks: 2, alignment: [6, 24, 42] },
  { version: 9, dataCodewords: 232, ecCodewordsPerBlock: 30, blocks: 2, alignment: [6, 26, 46] },
];

function appendBits(bits: number[], value: number, length: number): void {
  for (let index = length - 1; index >= 0; index -= 1) {
    bits.push((value >>> index) & 1);
  }
}

function chooseVersion(byteLength: number): QrVersionSpec {
  for (const spec of VERSION_SPECS) {
    const charCountBits = spec.version <= 9 ? 8 : 16;
    const requiredBits = 4 + charCountBits + byteLength * 8;
    if (requiredBits <= spec.dataCodewords * 8) {
      return spec;
    }
  }
  throw new Error('qr_payload_too_large_for_phone_link');
}

function encodeDataCodewords(text: string, spec: QrVersionSpec): number[] {
  const bytes = Array.from(new TextEncoder().encode(text));
  const bits: number[] = [];
  appendBits(bits, BYTE_MODE, 4);
  appendBits(bits, bytes.length, spec.version <= 9 ? 8 : 16);
  bytes.forEach((byte) => appendBits(bits, byte, 8));

  const capacityBits = spec.dataCodewords * 8;
  const terminator = Math.min(4, capacityBits - bits.length);
  appendBits(bits, 0, terminator);
  while (bits.length % 8 !== 0) {
    bits.push(0);
  }

  const codewords: number[] = [];
  for (let index = 0; index < bits.length; index += 8) {
    let value = 0;
    for (let bitIndex = 0; bitIndex < 8; bitIndex += 1) {
      value = (value << 1) | bits[index + bitIndex];
    }
    codewords.push(value);
  }
  for (let pad = 0; codewords.length < spec.dataCodewords; pad += 1) {
    codewords.push(pad % 2 === 0 ? 0xec : 0x11);
  }
  return codewords;
}

function buildGfTables(): { exp: number[]; log: number[] } {
  const exp = new Array<number>(512).fill(0);
  const log = new Array<number>(256).fill(0);
  let value = 1;
  for (let index = 0; index < 255; index += 1) {
    exp[index] = value;
    log[value] = index;
    value <<= 1;
    if (value & 0x100) {
      value ^= 0x11d;
    }
  }
  for (let index = 255; index < 512; index += 1) {
    exp[index] = exp[index - 255];
  }
  return { exp, log };
}

const GF = buildGfTables();

function gfMultiply(left: number, right: number): number {
  if (left === 0 || right === 0) {
    return 0;
  }
  return GF.exp[GF.log[left] + GF.log[right]];
}

function buildRsGenerator(degree: number): number[] {
  let coefficients = [1];
  for (let degreeIndex = 0; degreeIndex < degree; degreeIndex += 1) {
    const next = new Array<number>(coefficients.length + 1).fill(0);
    coefficients.forEach((coefficient, index) => {
      next[index] ^= gfMultiply(coefficient, GF.exp[degreeIndex]);
      next[index + 1] ^= coefficient;
    });
    coefficients = next;
  }
  return coefficients.slice(0, degree).reverse();
}

function computeEcc(data: number[], degree: number): number[] {
  const generator = buildRsGenerator(degree);
  const remainder = new Array<number>(degree).fill(0);
  data.forEach((codeword) => {
    const factor = codeword ^ remainder.shift()!;
    remainder.push(0);
    generator.forEach((coefficient, index) => {
      remainder[index] ^= gfMultiply(coefficient, factor);
    });
  });
  return remainder;
}

function interleaveBlocks(dataCodewords: number[], spec: QrVersionSpec): number[] {
  const dataBlockLength = spec.dataCodewords / spec.blocks;
  const dataBlocks: number[][] = [];
  const eccBlocks: number[][] = [];
  for (let block = 0; block < spec.blocks; block += 1) {
    const start = block * dataBlockLength;
    const dataBlock = dataCodewords.slice(start, start + dataBlockLength);
    dataBlocks.push(dataBlock);
    eccBlocks.push(computeEcc(dataBlock, spec.ecCodewordsPerBlock));
  }

  const result: number[] = [];
  for (let index = 0; index < dataBlockLength; index += 1) {
    dataBlocks.forEach((block) => result.push(block[index]));
  }
  for (let index = 0; index < spec.ecCodewordsPerBlock; index += 1) {
    eccBlocks.forEach((block) => result.push(block[index]));
  }
  return result;
}

function createEmptyMatrix(size: number): { modules: boolean[][]; reserved: boolean[][] } {
  return {
    modules: Array.from({ length: size }, () => new Array<boolean>(size).fill(false)),
    reserved: Array.from({ length: size }, () => new Array<boolean>(size).fill(false)),
  };
}

function setModule(
  modules: boolean[][],
  reserved: boolean[][],
  x: number,
  y: number,
  value: boolean,
  isReserved = true,
): void {
  if (y < 0 || y >= modules.length || x < 0 || x >= modules.length) {
    return;
  }
  modules[y][x] = value;
  if (isReserved) {
    reserved[y][x] = true;
  }
}

function drawFinder(modules: boolean[][], reserved: boolean[][], left: number, top: number): void {
  for (let y = -1; y <= 7; y += 1) {
    for (let x = -1; x <= 7; x += 1) {
      const xx = left + x;
      const yy = top + y;
      const inFinder = x >= 0 && x <= 6 && y >= 0 && y <= 6;
      const isBlack = inFinder && (
        x === 0 || x === 6 || y === 0 || y === 6 || (x >= 2 && x <= 4 && y >= 2 && y <= 4)
      );
      setModule(modules, reserved, xx, yy, isBlack);
    }
  }
}

function drawAlignment(modules: boolean[][], reserved: boolean[][], centerX: number, centerY: number): void {
  if (reserved[centerY][centerX]) {
    return;
  }
  for (let y = -2; y <= 2; y += 1) {
    for (let x = -2; x <= 2; x += 1) {
      const distance = Math.max(Math.abs(x), Math.abs(y));
      setModule(modules, reserved, centerX + x, centerY + y, distance !== 1);
    }
  }
}

function drawFunctionPatterns(modules: boolean[][], reserved: boolean[][], spec: QrVersionSpec): void {
  const size = modules.length;
  drawFinder(modules, reserved, 0, 0);
  drawFinder(modules, reserved, size - 7, 0);
  drawFinder(modules, reserved, 0, size - 7);

  for (let index = 8; index < size - 8; index += 1) {
    const value = index % 2 === 0;
    setModule(modules, reserved, 6, index, value);
    setModule(modules, reserved, index, 6, value);
  }

  spec.alignment.forEach((y) => {
    spec.alignment.forEach((x) => drawAlignment(modules, reserved, x, y));
  });

  setModule(modules, reserved, 8, size - 8, true);
  reserveFormatAreas(reserved);
  if (spec.version >= 7) {
    reserveVersionAreas(reserved);
  }
}

function reserveFormatAreas(reserved: boolean[][]): void {
  const size = reserved.length;
  for (let index = 0; index <= 8; index += 1) {
    if (index !== 6) {
      reserved[8][index] = true;
      reserved[index][8] = true;
    }
  }
  for (let index = 0; index < 8; index += 1) {
    reserved[8][size - 1 - index] = true;
    reserved[size - 1 - index][8] = true;
  }
}

function reserveVersionAreas(reserved: boolean[][]): void {
  const size = reserved.length;
  for (let index = 0; index < 6; index += 1) {
    for (let offset = 0; offset < 3; offset += 1) {
      reserved[index][size - 11 + offset] = true;
      reserved[size - 11 + offset][index] = true;
    }
  }
}

function maskBit(x: number, y: number): boolean {
  return (x + y) % 2 === 0;
}

function drawData(modules: boolean[][], reserved: boolean[][], codewords: number[]): void {
  const bits = codewords.flatMap((codeword) => {
    const next: number[] = [];
    appendBits(next, codeword, 8);
    return next;
  });
  const size = modules.length;
  let bitIndex = 0;
  let upward = true;
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) {
      right -= 1;
    }
    for (let vertical = 0; vertical < size; vertical += 1) {
      const y = upward ? size - 1 - vertical : vertical;
      for (let offset = 0; offset < 2; offset += 1) {
        const x = right - offset;
        if (reserved[y][x]) {
          continue;
        }
        const bit = bitIndex < bits.length ? bits[bitIndex] === 1 : false;
        modules[y][x] = bit !== maskBit(x, y);
        bitIndex += 1;
      }
    }
    upward = !upward;
  }
}

function computeBch(value: number, generator: number, degree: number): number {
  let bits = value << degree;
  const generatorDegree = bitLength(generator) - 1;
  while (bitLength(bits) - 1 >= generatorDegree) {
    bits ^= generator << (bitLength(bits) - 1 - generatorDegree);
  }
  return (value << degree) | bits;
}

function bitLength(value: number): number {
  let length = 0;
  for (let current = value; current > 0; current >>>= 1) {
    length += 1;
  }
  return length;
}

function drawFormatBits(modules: boolean[][]): void {
  const size = modules.length;
  const formatBits = computeBch((LOW_ECL_FORMAT_BITS << 3) | MASK_PATTERN, FORMAT_GENERATOR, 10) ^ FORMAT_MASK;
  for (let index = 0; index < 15; index += 1) {
    const bit = ((formatBits >>> index) & 1) !== 0;
    if (index < 6) {
      modules[index][8] = bit;
    } else if (index === 6) {
      modules[7][8] = bit;
    } else if (index === 7) {
      modules[8][8] = bit;
    } else if (index === 8) {
      modules[8][7] = bit;
    } else {
      modules[8][14 - index] = bit;
    }

    if (index < 8) {
      modules[8][size - 1 - index] = bit;
    } else {
      modules[size - 15 + index][8] = bit;
    }
  }
}

function drawVersionBits(modules: boolean[][], version: number): void {
  if (version < 7) {
    return;
  }
  const size = modules.length;
  const versionBits = computeBch(version, VERSION_GENERATOR, 12);
  for (let index = 0; index < 18; index += 1) {
    const bit = ((versionBits >>> index) & 1) !== 0;
    const x = size - 11 + (index % 3);
    const y = Math.floor(index / 3);
    modules[y][x] = bit;
    modules[x][y] = bit;
  }
}

function buildQrMatrix(text: string): QrMatrix {
  const bytes = new TextEncoder().encode(text);
  const spec = chooseVersion(bytes.length);
  const dataCodewords = encodeDataCodewords(text, spec);
  const allCodewords = interleaveBlocks(dataCodewords, spec);
  const size = 21 + (spec.version - 1) * 4;
  const { modules, reserved } = createEmptyMatrix(size);
  drawFunctionPatterns(modules, reserved, spec);
  drawData(modules, reserved, allCodewords);
  drawFormatBits(modules);
  drawVersionBits(modules, spec.version);
  return { size, modules };
}

export function createQrCodeSvgPath(text: string, quietZone = QUIET_ZONE): QrCodeSvgPath {
  const matrix = buildQrMatrix(text);
  const pathParts: string[] = [];
  matrix.modules.forEach((row, y) => {
    row.forEach((isBlack, x) => {
      if (isBlack) {
        pathParts.push(`M${x + quietZone},${y + quietZone}h1v1h-1z`);
      }
    });
  });
  return {
    path: pathParts.join(''),
    size: matrix.size,
    quietZone,
    viewBoxSize: matrix.size + quietZone * 2,
  };
}
