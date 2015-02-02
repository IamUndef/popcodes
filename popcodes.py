#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import sys
import locale
import random

from getopt import getopt, GetoptError
from shutil import copyfile

HELP_MESSAGE = u'''Утилита генерации опкодов Python 2.7

Использование: python popcodes.py file [version]

Описание параметров:
    file    заголовочный файл с опкодами (opcode.h)
    version версия для заголовочного файла со сгенерированными опкодами
'''


def generate_opcode_value(value, values, start, stop, step=1, isAppend=True):
    result = None
    freeValues = list(set(range(start, stop + 1, step)) - set(values))
    if freeValues and (len(freeValues) != 1 or freeValues[0] != value):
        while result is None or result == value:
            result = random.choice(freeValues)
    if result is not None and isAppend:
        values.append(result)
    return result


def test_opcode_values(opcodes):
    values = [(name, opcode['new'], opcode['value']) for name, opcode in opcodes.iteritems()]
    for name, new, old in values:
        if new is None:
            raise Exception(u'Opcode %s value is none' % name)
        elif new == old and name != 'HAVE_ARGUMENT':
            raise Exception(u'Opcode %s value is equal to old value' % name)
        else:
            errors = filter(lambda opcode: name != opcode[0] and new == opcode[1], values)
            if errors:
                errors.insert(0, (name, new, old))
                raise Exception(os.linesep.join([u'Intersection of opcodes'] +
                                                [u'name: %s, code: %s' % (opcode[0], opcode[1]) for opcode in errors]))
    for name in ('SLICE', 'STORE_SLICE', 'DELETE_SLICE'):
        value = opcodes[name]['new']
        errors = filter(lambda opcode: opcode[1] in (value + 1, value + 2, value + 3), values)
        if errors:
            raise Exception(os.linesep.join([u'Intersection with %s (code: %s) sequence' % (name, value)] +
                                            [u'name: %s, code: %s' % (opcode[0], opcode[1]) for opcode in errors]))
    if (opcodes['CALL_FUNCTION_VAR']['new'] - opcodes['CALL_FUNCTION']['new']) & 3 != 1:
        raise Exception('Opcode CALL_FUNCTION_VAR value error')
    elif opcodes['CALL_FUNCTION_KW']['new'] != opcodes['CALL_FUNCTION_VAR']['new'] + 1:
        raise Exception('Opcode CALL_FUNCTION_KW value error')
    elif opcodes['CALL_FUNCTION_VAR_KW']['new'] != opcodes['CALL_FUNCTION_VAR']['new'] + 2:
        raise Exception('Opcode CALL_FUNCTION_VAR_KW value error')


def to_unicode(value):
    try:
        return unicode(value)
    except UnicodeError:
        return str(value).decode(locale.getpreferredencoding())


if __name__ == "__main__":
    exceptionMessage = ''
    isUsageException = False
    try:
        _, arguments = getopt(sys.argv[1:], '')
        if not arguments:
            print HELP_MESSAGE
        else:
            opcodeFile = arguments[0]
            opcodeVersion = arguments[1] if len(arguments) > 1 else ''
            with open(opcodeFile) as f:
                opcodeLines = f.readlines()
            # Получаем опкоды и их значения
            opcodes = {}
            for index, line in enumerate(opcodeLines):
                matchObject = re.match(r'^#define\s+([a-zA-Z][\w]*)\s+(\d+).*$', line)
                if matchObject:
                    name, value = matchObject.groups()
                    opcodes[name] = {'index': index, 'value': int(value), 'new': None}
            # Находим значение опкодов с аргументами и максимальное значение
            argOpcodeValue = opcodes['HAVE_ARGUMENT']['value']
            maxOpcodeValue = max([opcode['value'] for opcode in opcodes.itervalues()])
            opcodes['HAVE_ARGUMENT']['new'] = argOpcodeValue
            opcodeValues = [argOpcodeValue]
            # Обрабатываем опкоды SLICE, STORE_SLICE, DELETE_SLICE
            for name in ('SLICE', 'STORE_SLICE', 'DELETE_SLICE'):
                # Необходимо получить последовательность кодов: код, код + 1, код + 2, код + 3
                value = generate_opcode_value(opcodes[name]['value'], opcodeValues, 0, argOpcodeValue - 4, 4)
                if value is not None:
                    opcodes[name]['new'] = value
                    opcodeValues.extend((value + 1, value + 2, value + 3))
            # Обрабатываем опкоды CALL_FUNCTION, CALL_FUNCTION_VAR, CALL_FUNCTION_KW, CALL_FUNCTION_VAR_KW
            opcodes['CALL_FUNCTION']['new'] = generate_opcode_value(opcodes['CALL_FUNCTION']['value'], opcodeValues,
                                                                    argOpcodeValue, maxOpcodeValue)
            # Необходимо выполнение условия (CALL_FUNCTION_VAR - CALL_FUNCTION) & 3 == 1
            value = None
            while value is None or (value - opcodes['CALL_FUNCTION']['new']) & 3 != 1:
                # Необходимо получить последовательность кодов: код, код + 1, код + 2
                value = generate_opcode_value(opcodes['CALL_FUNCTION_VAR']['value'], opcodeValues, argOpcodeValue,
                                              maxOpcodeValue - 2, isAppend=False)
                if value is None:
                    break
            if value is not None:
                opcodes['CALL_FUNCTION_VAR']['new'] = value
                opcodes['CALL_FUNCTION_KW']['new'] = value + 1
                opcodes['CALL_FUNCTION_VAR_KW']['new'] = value + 2
                opcodeValues.extend((value, value + 1, value + 2))
            # Обрабатываем остальные опкоды
            for opcode in opcodes.itervalues():
                if opcode['new'] is None:
                    if opcode['value'] < argOpcodeValue:
                        value = generate_opcode_value(opcode['value'], opcodeValues, 0, argOpcodeValue - 1)
                    else:
                        value = generate_opcode_value(opcode['value'], opcodeValues, argOpcodeValue, maxOpcodeValue)
                    opcode['new'] = value
            test_opcode_values(opcodes)
            for opcode in opcodes.itervalues():
                opcodeLines[opcode['index']] = opcodeLines[opcode['index']].replace(str(opcode['value']),
                                                                                    str(opcode['new']), 1)
            if not os.path.isfile('%s.orig' % opcodeFile):
                copyfile(opcodeFile, '%s.orig' % opcodeFile)
            with open(opcodeFile, 'w') as f:
                f.writelines(opcodeLines)
            if opcodeVersion:
                indexVersion = 1
                while os.path.isfile('%s.%s.%s' % (opcodeFile, opcodeVersion, indexVersion)):
                    indexVersion += 1
                copyfile(opcodeFile, '%s.%s.%s' % (opcodeFile, opcodeVersion, indexVersion))
    except GetoptError as e:
        exceptionMessage = to_unicode(e)
        isUsageException = True
    except Exception as e:
        exceptionMessage = to_unicode(e)
    if exceptionMessage:
        print u'Error: %s' % exceptionMessage
        if isUsageException:
            print HELP_MESSAGE
        sys.exit(-1)