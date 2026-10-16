import json
import pytest
from tools.social_parser import detect_platform, scan_directory, extract_material, generate_report, read_text_file


@pytest.mark.parametrize('filename,platform',[('微博.txt','weibo'),('xhs.json','xiaohongshu'),('wechat.png','moments'),
    ('dy_1.jpg','douyin'),('ig_1.jpg','instagram'),('tweet.txt','twitter'),('bili.json','bilibili'),('random.txt','未知平台')])
def test_platform_is_filename_hint(filename,platform):assert detect_platform(filename)==platform


def test_inventory_excludes_hidden_and_report(tmp_path):
    for name in ['a.png','b.txt','c.bin','report.md','.hidden.txt']:(tmp_path/name).write_text('x')
    result=scan_directory(tmp_path)
    assert [r['name'] for r in result['texts']]==['b.txt']
    assert [r['name'] for r in result['images']]==['a.png']
    assert [r['name'] for r in result['others']]==['c.bin']


def test_all_posts_preserve_negation_and_author(tmp_path):
    p=tmp_path/'posts.json'
    posts=[{'author':'other','text':'不是喜欢他，是不喜欢他','id':i} for i in range(60)]
    p.write_text(json.dumps(posts),encoding='utf-8')
    result=extract_material(p)
    assert len(result)==60 and result[0]['raw']==posts[0]
    assert result[-1]['source_refs'][0]['locator']=='record:60'
    report=generate_report(tmp_path,'小美')
    assert '公开动态不等于' in report and '积极信号' not in report


def test_truncation_and_unparsed_errors_visible(tmp_path):
    p=tmp_path/'long.txt';p.write_text('x'*5001)
    result=extract_material(p)[0]
    assert result['truncated'] and result['total_chars']==5001
    assert '截断' in read_text_file(p)
    (tmp_path/'bad.json').write_text('{')
    assert 'unparsed' in generate_report(tmp_path)


def test_csv_multiline_provenance(tmp_path):
    p=tmp_path/'posts.csv';p.write_text('author,text\nx,"first\nsecond"',encoding='utf-8',newline='')
    row=extract_material(p)[0]
    assert row['raw']['text']=='first\nsecond'
    assert row['source_refs'][0]['locator']=='csv-row-ending-line:3'
