#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md2wechat.py v2 — 微信公众号排版「终极方案」
用法:  python md2wechat.py 文章.md
生成:  同目录下的 文章.wechat.html
然后:  浏览器打开 .wechat.html -> Ctrl+A 全选 -> Ctrl+C 复制
       -> 微信PC版打开 mp.weixin.qq.com 编辑器 -> Ctrl+V 粘贴 -> 预览 -> 群发

规则:
  1. 第一行 '# 标题' 作为文章标题(仅作标识，不渲染进正文，避免与公众号标题栏重复)
  2. '##' -> 正文一级小节标题(加粗深色,无橙边) ; '###' -> 正文二级小节标题
  3. 全部内联 style，公众号编辑器会清洗外链 CSS，内联样式才能保住排版
  4. 正文字号 16px(与微信原生默认一致，比旧版15px更清晰)，行距 1.8

注意: 公众号标题栏请手动填 .md 第一行的标题文字，正文里不要再出现它。
"""
import sys, re, os

# 微信友好样式（全部内联，统一基准，避免每篇不一致）
STYLE = {
    'p':    'font-size:16px;line-height:1.8;color:#2b2b2b;letter-spacing:0.5px;margin:0 0 1.2em 0;',
    'h2':   'font-size:18px;font-weight:bold;color:#1a1a1a;margin:30px 0 14px;line-height:1.5;',
    'h3':   'font-size:16px;font-weight:bold;color:#333;margin:24px 0 10px;',
    'quote':'background:#f6f6f6;border-left:4px solid #ff8a00;padding:14px 16px;color:#666;margin:18px 0;font-size:15px;line-height:1.8;border-radius:4px;',
    'hr':   'border:none;border-top:1px solid #e8e8e8;margin:26px 0;',
    'img':  'max-width:100%;display:block;margin:14px auto;border-radius:6px;',
    'li':   'font-size:16px;line-height:1.8;color:#2b2b2b;margin:6px 0;',
    'a':    'color:#576b95;text-decoration:none;',
}

def inline(text):
    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)',
                 r'<img src="\2" alt="\1" style="' + STYLE['img'] + '"/>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                 r'<a href="\2" style="' + STYLE['a'] + '">\1</a>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`',
                  r'<code style="background:#f2f2f2;padding:2px 4px;border-radius:3px;font-size:13px;">\1</code>', text)
    return text

def convert(md):
    lines = md.split('\n')
    out = []
    i = 0
    list_type = [None]
    para = []

    def flush_para():
        if para:
            out.append('<p style="%s">%s</p>' % (STYLE['p'], inline(' '.join(para))))
            para.clear()

    def close_list():
        if list_type[0] is not None:
            out.append('</%s>' % list_type[0])
            list_type[0] = None

    first = True
    while i < len(lines):
        line = lines[i].rstrip()
        # 标题
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            flush_para(); close_list()
            level = len(m.group(1))
            # 一级标题(#)作为文章标题，不渲染进正文，避免与公众号标题栏重复
            if level == 1:
                i += 1; continue
            tag = 'h2' if level == 2 else 'h3'
            out.append('<%s style="%s">%s</%s>' % (tag, STYLE[tag], inline(m.group(2)), tag))
            i += 1; continue
        # 分割线
        if line.strip() in ('---', '***', '___'):
            flush_para(); close_list()
            out.append('<hr style="%s"/>' % STYLE['hr']); i += 1; continue
        # 引用（多行合并）
        if line.startswith('>'):
            flush_para(); close_list()
            q = []
            while i < len(lines) and lines[i].startswith('>'):
                q.append(re.sub(r'^>\s?', '', lines[i]))
                i += 1
            out.append('<blockquote style="%s">%s</blockquote>' % (STYLE['quote'], inline(' '.join(q))))
            continue
        # 无序列表
        m = re.match(r'^[-*]\s+(.*)$', line)
        if m:
            flush_para()
            if list_type[0] != 'ul':
                close_list(); out.append('<ul style="padding-left:22px;margin:12px 0;">'); list_type[0] = 'ul'
            out.append('<li style="%s">%s</li>' % (STYLE['li'], inline(m.group(1)))); i += 1; continue
        # 有序列表
        m = re.match(r'^\d+\.\s+(.*)$', line)
        if m:
            flush_para()
            if list_type[0] != 'ol':
                close_list(); out.append('<ol style="padding-left:22px;margin:12px 0;">'); list_type[0] = 'ol'
            out.append('<li style="%s">%s</li>' % (STYLE['li'], inline(m.group(1)))); i += 1; continue
        # 空行
        if line.strip() == '':
            flush_para(); close_list(); i += 1; continue
        # 普通段落
        para.append(line); i += 1
    flush_para(); close_list()
    return '\n'.join(out)

def main():
    if len(sys.argv) < 2:
        print("用法: python md2wechat.py 文章.md")
        sys.exit(1)
    src = sys.argv[1]
    if not os.path.exists(src):
        print("文件不存在: " + src)
        sys.exit(1)
    with open(src, 'r', encoding='utf-8') as f:
        md = f.read()
    html = convert(md)
    base, _ = os.path.splitext(src)
    dst = base + '.wechat.html'
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(html)
    print("已生成微信排版 HTML: " + dst)

if __name__ == '__main__':
    main()
