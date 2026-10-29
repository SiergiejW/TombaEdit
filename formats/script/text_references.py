"""Conservative WSS message selectors, including variable-supplied dialogue.

This computes an upper bound, not trigger reachability: every instruction
reachable from any entry contributes definitions, even across mutually exclusive
branches. A finite result is a dynamic selection, not a proven playthrough.
"""
from collections import defaultdict


def selectors(script, limit=256, actions=(4, 8), base_arg=2, line_arg=3):
    definitions = defaultdict(list)
    talks = []
    for i, ins in enumerate(script.instructions):
        if ins.name == 'ARGS':
            # Arguments are loaded simultaneously through a temporary buffer.
            for n, operand in enumerate(ins.operands):
                definitions[f'r{n}'].append(('MOV', (operand,)))
            if i + 1 < len(script.instructions):
                call = script.instructions[i + 1]
                if call.offset == ins.offset + ins.size and call.name == 'ObjAction' and len(ins.operands) >= 4:
                    talks.append(ins)
        elif ins.name == 'SWAP':
            a, b = ins.operands
            definitions[a].append(('MOV', (b,)))
            definitions[b].append(('MOV', (a,)))
        elif ins.name in ('MOV', 'RAND', 'INC', 'DEC', 'NOT', 'NEG',
                          'ADD', 'SUB', 'MUL', 'DIV', 'MOD', 'AND', 'OR', 'XOR', 'LOOP'):
            dest = ins.operands[0]
            op = 'DEC' if ins.name == 'LOOP' else ins.name
            operands = ins.operands[1:] if op == 'MOV' else (dest,) + ins.operands[1:]
            definitions[dest].append((op, operands))
        elif script.code[ins.offset] >= 0x80:
            # Native operations return values in the argument/result slots.
            # Do not let an earlier argument survive as a known return value.
            for n in range(16):
                definitions[f'r{n}'].append(('UNKNOWN', ()))

    # scriptStart zeroes all 80 variables. Calls share them; PUSH/POP can
    # restore previous values but cannot introduce a value absent here.
    values = {name: {0} for name in definitions}

    def read(operand):
        try:
            return {int(operand)}
        except ValueError:
            return values.get(operand, {0})

    def evaluate(op, operands):
        if op in ('UNKNOWN', 'RAND'):
            return None
        args = [read(o) for o in operands]
        if any(a is None for a in args):
            return None
        if op == 'MOV':
            return args[0]
        out = set()
        for a in args[0]:
            for b in args[1] if len(args) > 1 else (0,):
                if op == 'INC': v = a + 1
                elif op == 'DEC': v = a - 1
                elif op == 'NOT': v = ~a
                elif op == 'NEG': v = -a
                elif op == 'ADD': v = a + b
                elif op == 'SUB': v = a - b
                elif op == 'MUL': v = a * b
                elif op in ('DIV', 'MOD'):
                    if b == 0:
                        return None
                    q = abs(a) // abs(b) * (-1 if (a < 0) != (b < 0) else 1)
                    v = q if op == 'DIV' else a - q * b
                elif op == 'AND': v = a & b
                elif op == 'OR': v = a | b
                elif op == 'XOR': v = a ^ b
                else: return None
                out.add(((v + 0x80000000) & 0xFFFFFFFF) - 0x80000000)
                if len(out) > limit:
                    return None
        return out

    changed = True
    while changed:
        changed = False
        for dest, defs in definitions.items():
            if values[dest] is None:
                continue
            merged = set(values[dest])
            for op, operands in defs:
                result = evaluate(op, operands)
                if result is None:
                    merged = None
                    break
                merged.update(result)
                if len(merged) > limit:
                    merged = None
                    break
            if merged != values[dest]:
                values[dest] = merged
                changed = True
    result = []
    for ins in talks:
        action = read(ins.operands[1])
        base, line = (read(ins.operands[n]) if n < len(ins.operands) else None for n in (base_arg, line_arg))
        if action is None or action & set(actions):
            result.append(dict(offset=ins.offset, bases=base, lines=line,
                               bounded=action is not None and base is not None and line is not None))
    return result
