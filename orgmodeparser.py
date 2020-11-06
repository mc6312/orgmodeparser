#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" orgmodeparser.py

    Copyright 2020 MC-6312 <mc6312@gmail.com>

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>."""


""" Минимальный набор для разбора файлов Emacs Org Mode."""


import sys
import os.path
import re


VERSION = '0.5'


class OrgNode():
    """Базовый класс.

    text        - строка (содержимое);
                  подробности зависят от класса-потомка;
    children    - список дочерних ветвей."""

    def __init__(self, text):
        self.text = text
        self.children = []

    def find_child_by_text(self, text, childtype):
        """Ищет в списке children первый дочерний
        элемент, поле text которого равно параметру text,
        и возвращает найденный экземпляр OrgNode.
        Сравнение регистро-зависимое, поиск НЕ рекурсивный.
        Если параметр childtype не None, проверяются
        также типы дочерних элементов на совпадение с childtype.
        Если метод ничего не находит - возвращает None."""

        for child in self.children:
            if child.text != text:
                continue

            # НЕ isinstance(child, childtype) потому, что нужно
            # точное сравнение, а не совпадение класса-потомка с родителем
            if childtype is not None and type(child) is not childtype:
                continue

            return child

    def __repr_children__(self):
        return 'children=[...%d item(s)...]' % len(self.children)

    def __repr_values__(self):
        # потомок, имеющий дополнительные поля, должен возвращать словарь
        # вида {'name':'value'}
        return {}

    def __repr__(self):
        vd = self.__repr_values__()
        if self.text is not None:
            vd['text'] = self.text

        return '%s(%s%s)' % (
            self.__class__.__name__,
            '' if not vd else ', '.join(map(lambda a: '%s="%s"' % (a[0], a[1]), vd.items())),
            self.__repr_children__())

    def __str__(self):
        """Класс-потомок должен полностью перекрывать этот метод, если
        содержимое должно содержать что-то, кроме простого текста."""

        return self.text


class OrgHeadlineNode(OrgNode):
    """Заголовок блока.
    В поле text - текст заголовка.
    В текущей версии модуля служебные слова (кроме TODO/DONE,
    приоритетов и тэгов) и прочее считаются частью текста заголовка.

    Поля экземпляра класса:
    text        - текст заголовка;
    done        - None или булевское значение:
                  True для DONE, False для TODO;
    priority    - None или строка "A"/"B"/"C";
    tags        - тэги - список строк (м.б. пустым);
                  т.к. порядок тэгов должен быть тот же, что в .org-файле,
                  и формат допускает пустые пару "::", здесь используем
                  список, а не множество."""

    # тэги м.б. только в конце строки!
    __RX_HEADLINE = re.compile('^((TODO|DONE)?\s+)?(\[#(A|B|C)\]\s+)?(.*?)?(:(\S*):)?\s*$', re.UNICODE)

    def __init__(self, text):
        self.done = None
        self.priority = None
        self.tags = []

        rm = self.__RX_HEADLINE.match(text)
        if rm:
            sdone = rm.group(2)
            if sdone == 'DONE':
                self.done = True
            elif sdone == 'TODO':
                self.done = False

            spri = rm.group(4)
            if spri is not None:
                self.priority = spri

            stags = rm.group(7)
            if stags is not None:
                # на пустые тэги ("::") не проверяем -
                # формат это допускает, значит, пусть лежат как есть
                self.tags = stags.split(':')

            # пробелы на концах текста убираем - тут они нам не нужны,
            # а Emacs их втыкает перед тэгами ради бессмысленного выравнивания
            # для правильной работы что Emacs, что этого парсера
            # они не обязательны, а память жруть
            text = rm.group(5).strip()

        super().__init__(text)

    def __repr_values__(self):
        return {'done':str(self.done), 'priority':str(self.priority)}

    def __str__(self):
        # Внимание! Символы "*" при необходимости должны добавляться
        # где-то уровнем выше, т.к. требуют рекурсивного обхода дерева
        # с учётом уровня вложенности

        return '%s%s%s%s' % (
            '' if self.done is None else 'TODO ' if not self.done else 'DONE ',
            '' if self.priority is None else '[#%s] ' % self.priority,
            self.text,
            '' if not self.tags else ' :%s:' % (':'.join(self.tags)),
            )


class OrgTextNode(OrgNode):
    """Простой текст.
    В поле text - весь текст соотв. строки."""

    pass


class OrgCommentNode(OrgNode):
    """Комментарий.
    В поле text - единственный элемент, весь текст соотв. строки."""

    def __str__(self):
        return '# %s' % self.text


class OrgDirectiveNode(OrgCommentNode):
    """Директива (из строки вида #+DIRECTIVE: values).
    Поля:
    name    - имя директивы,
    text    - аргументы директивы (остаток строки после ":")."""

    def __init__(self, text, name):
        super().__init__(text)
        self.name = name

    def __str__(self):
        return '#+%s: %s' % (self.name, self.text)


class OrgParseIter():
    """Класс итератора для синтаксического разбора org-файла."""

    class TokenInfo():
        """Синтаксический элемент файла.
        Поля:
        type    - int, значение HEADLINE/...;
        line    - int, номер строки в org-файле;
        value   - None или строка (содержимое строки файла,
                  без префикса "***"/"#"/..., детали зависят от type:
                  HEADLINE  - текст заголовка блока;
                  HLEXIT    - None;
                  TEXT      - вся строка из файла;
                  COMMENT   - вся строка из файла без начального "# ";
                  DIRECTIVE - имя_директивы (текст между "+" и ":"),
                              после этого токена должен следовать
                              токен с type=TEXT и аргументами директивы."""

        __slots__ = 'type', 'line', 'value'

        HEADLINE, HLEXIT, TEXT, COMMENT, DIRECTIVE = range(5)

        TKN_NAME = ('HEADLINE', 'HLEXIT', 'TEXT', 'COMMENT', 'DIRECTIVE')

        def __init__(self, type_, line, value):
            self.type, self.line, self.value = type_, line, value

        def __repr__(self):
            return '%s(type=%s, line=%d%s)' % (self.__class__.__name__,
                self.TKN_NAME[self.type],
                self.line,
                '' if self.value is None else ', value="%s"' % self.value)

    def __init__(self, fileobj):
        self.fileobj = fileobj
        self.buf = None
        self.buflen = 0
        self.bufpos = 0

        self.level = 0
        self.oldlevel = 0

        self.hold = []

        self.lineno = 0

    def __iter__(self):
        return self

    def __next__(self):
        """Возвращает кортеж из трёх элементов:
        токен (int),
        уровень вложенности (int),
        значение (str).
        Если файл кончился, генерирует исключение StopIteration."""

        # возвращаем "отложенные" токены
        if self.hold:
            return self.hold.pop()

        if self.buf is None or self.bufpos >= self.buflen:
            # вот тут и может вылезти StopIteration
            try:
                # пробельные символы в начале строки ОСТАВЛЯЕМ!
                # они учитываются Emacs в случае (вложенных) списков и т.п.
                self.buf = next(self.fileobj).rstrip()
                self.lineno += 1
            except StopIteration:
                if self.hold:
                    return self.hold.pop()
                else:
                    raise StopIteration

            self.buflen = len(self.buf)
            self.bufpos = 0

        if self.buflen == 0:
            return self.TokenInfo(self.TokenInfo.TEXT, self.lineno, '')

        def __skip_space():
            while self.bufpos < self.buflen and self.buf[self.bufpos].isspace(): self.bufpos += 1

        def __is_ctl_word(frompos, topos):
            """Проверка, содержит ли self.buf[frompos:topos] только заглавные символы
            латинского алфавита и символ "_".
            Возвращает True в случае соответствия, иначе - False."""

            while frompos < topos:
                if self.buf[frompos] not in '_ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                    return False

                frompos += 1

            return True

        if self.buf.startswith('*'):
            while self.bufpos < self.buflen and self.buf[self.bufpos] == '*': self.bufpos += 1

            # "заголовком" считается строка с цепочкой из "*" в начале И пробелом после "*"
            if self.bufpos >= self.buflen or not self.buf[self.bufpos].isspace():
                # не заголовок - просто строка с "*" в начале!
                self.bufpos = self.buflen
                return self.TokenInfo(self.TokenInfo.TEXT, self.lineno, self.buf)

            self.oldlevel = self.level

            # кол-во "*" в заголовке блока может быть произвольным
            # но level нельзя увеличивать больше, чем на 1 за раз
            if self.bufpos > self.level:
                self.level += 1
            elif self.bufpos < self.level:
                # а вот при уменьшении - уменьшаем на любое значение,
                # т.к. может быть возврат на несколько ступеней сразу
                self.level = self.bufpos

            __skip_space()

            headtkn = self.TokenInfo(self.TokenInfo.HEADLINE, self.lineno, self.buf[self.bufpos:])
            self.bufpos = self.buflen

            if self.level <= self.oldlevel:
                # HLEXITы должны приезжать перед следующим HEADLINE
                self.hold.append(headtkn)

                delta = self.oldlevel - self.level

                while delta > 0:
                    self.hold.append(self.TokenInfo(self.TokenInfo.HLEXIT, self.lineno, None))
                    delta -= 1

                return self.TokenInfo(self.TokenInfo.HLEXIT, self.lineno, None)
            else:
                return headtkn

        if self.buf.startswith('#'):
            self.bufpos += 1
            bufpos0 = self.bufpos

            tkn = self.TokenInfo.COMMENT

            # проверяем, не директива ли это вида "#+NAME: value(s)"
            if self.bufpos < self.buflen + 3 and self.buf[self.bufpos] == '+':
                while True:
                    self.bufpos += 1
                    if self.bufpos >= self.buflen:
                        break

                    colonpos = self.buf.find(':', self.bufpos)
                    if colonpos < 0:
                        break

                    if not __is_ctl_word(self.bufpos, colonpos):
                        break

                    # первым возвращаем токен DIRECTIVE с value='имя_директивы',
                    # за ним следует TEXT с аргументами
                    self.hold.append(self.TokenInfo(self.TokenInfo.TEXT, self.lineno, self.buf[colonpos + 1:].strip()))
                    self.bufpos = self.buflen
                    return self.TokenInfo(self.TokenInfo.DIRECTIVE, self.lineno, self.buf[bufpos0 + 1:colonpos])

            # не директива, а простой комментарий - откатываемся взад и вертаем всю строку
            self.bufpos = bufpos0
            __skip_space()
        else:
            tkn = self.TokenInfo.TEXT

        bufpos = self.bufpos
        self.bufpos = self.buflen

        return self.TokenInfo(tkn, self.lineno, self.buf[bufpos:])


class MinimalOrgParser(OrgNode):
    """Минимальный парсер org-файлов.

    Понимает только блоки с заголовками, комментарии, директивы и
    простой текст. Ключевые слова (кроме TODO/DONE и приоритетов в
    заголовках headlines), списки и всё прочее считается
    частью текстового содержимого соответствующих элементов."""

    def __init__(self, filename):
        super().__init__(filename)

        with open(filename, 'r') as orgfile:
            try:
                orgiter = OrgParseIter(orgfile)

                def parse_block(destnode, level):
                    prefix = None
                    dname = None

                    for nfo in orgiter:
                        if nfo.type == OrgParseIter.TokenInfo.HEADLINE:
                            destnode.children.append(OrgHeadlineNode(nfo.value))
                            parse_block(destnode.children[-1], level + 1)
                        elif nfo.type == OrgParseIter.TokenInfo.HLEXIT:
                            break
                        elif nfo.type == OrgParseIter.TokenInfo.COMMENT:
                            destnode.children.append(OrgCommentNode(nfo.value))
                        elif nfo.type == OrgParseIter.TokenInfo.DIRECTIVE:
                            prefix = nfo.type
                            dname = nfo.value
                        elif nfo.type == OrgParseIter.TokenInfo.TEXT:
                            if prefix == OrgParseIter.TokenInfo.DIRECTIVE:
                                node = OrgDirectiveNode(nfo.value, dname)
                            else:
                                node = OrgTextNode(nfo.value)

                            destnode.children.append(node)
                            prefix = None

                parse_block(self, 0)

            except StopIteration:
                pass

    def __dumps_node(self, node, level):
        buf = []

        for child in node.children:
            if isinstance(child, OrgHeadlineNode):
                c = '%s ' % ('*' * level,)
            else:
                c = ''

            buf.append('%s%s' % (c, str(child)))

            if child.children:
                buf.append(self.__dumps_node(child, level + 1))

        return '\n'.join(buf)

    def dumps(self, level):
        return self.__dumps_node(self, level)


def __debug_sample():
    fname = 'sample.org'
    #fname = 'bigsample.org'
    rootnode = MinimalOrgParser(fname)

    print(rootnode.dumps(1))

    return 0


if __name__ == '__main__':
    print('[debugging %s]' % __file__)
    __debug_sample()
