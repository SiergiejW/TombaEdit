"""Read-only MIPS I code and string navigation for INS overlays."""
import re
import struct
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget,
                             QPlainTextEdit, QLineEdit, QLabel, QTabWidget)
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtCore import Qt

REGS = ('zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra').split()


def instruction(word, address):
    op, rs, rt, rd, sa, fn = word >> 26, word >> 21 & 31, word >> 16 & 31, word >> 11 & 31, word >> 6 & 31, word & 63
    r = lambda i: '$' + REGS[i]
    imm = word & 65535
    signed = (imm ^ 0x8000) - 0x8000
    if word == 0:
        return 'nop'
    if op == 0:
        names = {0: 'sll', 2: 'srl', 3: 'sra', 4: 'sllv', 6: 'srlv', 7: 'srav',
                 8: 'jr', 9: 'jalr', 16: 'mfhi', 17: 'mthi', 18: 'mflo', 19: 'mtlo',
                 24: 'mult', 25: 'multu', 26: 'div', 27: 'divu', 32: 'add', 33: 'addu',
                 34: 'sub', 35: 'subu', 36: 'and', 37: 'or', 38: 'xor', 39: 'nor', 42: 'slt', 43: 'sltu'}
        name = names.get(fn)
        if name:
            if fn in (0, 2, 3): args = f'{r(rd)}, {r(rt)}, {sa}'
            elif fn in (8, 17, 19): args = r(rs)
            elif fn == 9: args = f'{r(rd)}, {r(rs)}'
            elif fn in (16, 18): args = r(rd)
            elif fn in (24, 25, 26, 27): args = f'{r(rs)}, {r(rt)}'
            elif fn in (4, 6, 7): args = f'{r(rd)}, {r(rt)}, {r(rs)}'
            else: args = f'{r(rd)}, {r(rs)}, {r(rt)}'
            return f'{name:7} {args}'
        if fn in (12, 13):
            return ('syscall' if fn == 12 else 'break') + f' 0x{word >> 6 & 0xfffff:X}'
    if op in (2, 3):
        return f'{"jal" if op == 3 else "j":7} 0x{((address + 4) & 0xf0000000) | ((word & 0x3ffffff) << 2):08X}'
    target = (address + 4 + signed * 4) & 0xffffffff
    if op in (4, 5):
        return f'{"beq" if op == 4 else "bne":7} {r(rs)}, {r(rt)}, 0x{target:08X}'
    if op in (6, 7) or op == 1 and rt in (0, 1, 16, 17):
        name = {6: 'blez', 7: 'bgtz'}.get(op) or {0: 'bltz', 1: 'bgez', 16: 'bltzal', 17: 'bgezal'}[rt]
        return f'{name:7} {r(rs)}, 0x{target:08X}'
    if op == 15:
        return f'lui     {r(rt)}, 0x{imm:04X}'
    if op in (8, 9, 10, 11, 12, 13, 14):
        name = {8:'addi',9:'addiu',10:'slti',11:'sltiu',12:'andi',13:'ori',14:'xori'}[op]
        return f'{name:7} {r(rt)}, {r(rs)}, {hex(imm) if op >= 12 else signed}'
    loads = {32:'lb',33:'lh',34:'lwl',35:'lw',36:'lbu',37:'lhu',38:'lwr',40:'sb',41:'sh',42:'swl',43:'sw',46:'swr',50:'lwc2',58:'swc2'}
    if op in loads:
        return f'{loads[op]:7} {r(rt) if op < 48 else "$c2r" + str(rt)}, {signed}({r(rs)})'
    if op in (16, 18):
        if op == 18 and rs >= 16:
            return f'gte     0x{word & 0x1ffffff:07X}'
        move = {0:'mfc',2:'cfc',4:'mtc',6:'ctc'}.get(rs)
        if move:
            return f'{move}{op - 16:<4} {r(rt)}, ${rd}'
    return f'.word   0x{word:08X}'


class InsView(QWidget):
    def __init__(self, data, base):
        super().__init__()
        self.data, self.base = bytes(data), base
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel('MIPS I | Address:'))
        self.address = QLineEdit(f'{base:08X}')
        self.address.returnPressed.connect(self.jump)
        row.addWidget(self.address)
        row.addWidget(QLabel('Read only. Function boundaries are inferred from stack prologues.'))
        layout.addLayout(row)
        split = QSplitter()
        tabs = QTabWidget()
        self.functions, self.strings = QListWidget(), QListWidget()
        tabs.addTab(self.functions, 'Functions'); tabs.addTab(self.strings, 'Strings')
        split.addWidget(tabs)
        self.code = QPlainTextEdit(); self.code.setReadOnly(True)
        self.code.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        split.addWidget(self.code); split.setSizes([300,800]); layout.addWidget(split)
        self.starts = [i for i in range(0,len(data)-3,4)
                       if struct.unpack_from('<I',data,i)[0] >> 16 == 0x27bd and data[i + 1] & 0x80]
        header = 0 not in self.starts
        if header: self.starts.insert(0,0)
        for at in self.starts:
            self.functions.addItem(('Header / data' if header and at == 0 else f'sub_{base + at:08X}') + f' | +{at:06X}')
        self.functions.currentRowChanged.connect(lambda row: self.show_address(base + self.starts[row]) if row >= 0 else None)
        for match in re.finditer(rb'[\x20-\x7e]{5,}\x00',self.data):
            self.strings.addItem(f'{base + match.start():08X}  {match[0][:-1].decode("ascii")[:100]}')
            self.strings.item(self.strings.count()-1).setData(Qt.ItemDataRole.UserRole,base + match.start())
        self.strings.currentRowChanged.connect(lambda row:self.show_address(self.strings.item(row).data(Qt.ItemDataRole.UserRole)) if row >= 0 else None)
        self.functions.setCurrentRow(1 if header and len(self.starts) > 1 else 0)

    def jump(self):
        try: self.show_address(int(self.address.text(),16))
        except ValueError: pass

    def show_address(self, address):
        start = max(0,min(len(self.data)-4,address-self.base)) & ~3
        end = min(len(self.data)-3,start+8192,next((i for i in self.starts if i>start),len(self.data)))
        self.address.setText(f'{self.base+start:08X}')
        lines = []
        for at in range(start,end,4):
            word = struct.unpack_from('<I',self.data,at)[0]
            lines.append(f'{self.base+at:08X}  {word:08X}  {instruction(word,self.base+at)}')
        self.code.setPlainText('\n'.join(lines))
