import zipfile
import xml.etree.ElementTree as ET

with zipfile.ZipFile('../DATS_Simulator_IDD_20261010.docx') as z:
    xml_content = z.read('word/document.xml')

root = ET.fromstring(xml_content)
# Find all text elements
namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

lines = []
for p in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
    texts = [t.text for t in p.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if t.text]
    if texts:
        lines.append(''.join(texts))

with open('idd_dump.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"Dumped {len(lines)} lines")
