# wine-grid-labeling-tool

LabelMe로 미리 어노테이션된 객체를 불러와, 객체별 `col`, `row`를 빠르게 지정하는 가벼운 GUI 툴입니다.

## 설치

```bash
git clone <your-repo-url>
cd wine-grid-labeling-tool
pip install -e .
```

## 실행

```bash
python run.py
```

또는:

```bash
wine-grid-labeler-gui
```

`run.py`는 프로젝트 루트의 `config.yml`을 읽어 줌 동작을 설정합니다.

## 워크플로우

1. 앱에서 이미지 폴더를 선택합니다.
2. 폴더 내 이미지 목록이 좌측 리스트에 표시됩니다.
3. 각 이미지에 대해:
   - 기존 LabelMe 객체(점으로 표시)를 불러옵니다.
   - `점 추가` 모드에서 새 점 객체를 추가할 수 있습니다.
   - `선택` 모드에서 객체를 클릭해 개별 `col`, `row`를 수정할 수 있습니다.
   - 드래그로 여러 객체를 선택하고 `col`을 일괄 지정할 수 있습니다.
   - `선택` 모드에서 `Ctrl + 드래그`를 하면 기존 선택에 누적 선택됩니다.
   - `마우스 휠`로 확대/축소할 수 있습니다.
   - 기본 드래그는 영역 선택이고, `Ctrl + 드래그`는 화면 이동입니다.
  - `Ctrl + Z`(macOS: `Cmd + Z`)로 직전 편집 작업을 되돌릴 수 있습니다.
  - `Ctrl + Y`(macOS: `Cmd + Y` 또는 `Cmd + Shift + Z`)로 되돌린 작업을 다시 실행할 수 있습니다.
   - 점을 더블클릭하면 팝업에서 `col`, `row`를 바로 수정할 수 있습니다.
  - 단축키: `R`(점 추가 모드), `E`(선택/편집 모드)
  - 단축키: `A`(이전 이미지), `D`(다음 이미지)
  - 영문 대/소문자 및 한글 IME 상태에서도 단축키 인식이 가능하도록 처리되어 있습니다.
  - `Ctrl + C / Ctrl + V`(macOS: `Cmd + C / Cmd + V`)로 선택 객체의 `col,row`를 복사/붙여넣기 할 수 있으며, 이미지를 바꿔도 복사 내용이 유지됩니다.
   - 선택 상태에서 숫자 키를 누르면 즉시 일괄 적용되며, 오른쪽에서 적용 대상(`col`/`row`)을 선택할 수 있습니다. (기본 `col`)
  - `Ctrl + ←/↑/→/↓`(macOS: `Cmd + ←/↑/→/↓`)는 선택 객체의 `col/row`를 1씩 일괄 증감합니다. (polygon 포함)
   - `col`이 변경되면 해당 column의 `row`는 자동으로 재배정됩니다.
   - 오른쪽 패널에 전체 점 수 / col 미지정 점 수 / row 미지정 점 수가 표시됩니다.
   - 오른쪽 `Grid Preview`는 검은 배경에서 `col,row` 좌표 기반으로 점/연결선을 항상 표시합니다.
   - 왼쪽 이미지 목록에서 편집/저장된 이미지는 체크(✓)와 초록색으로 표시됩니다.
   - 일괄 `col` 적용 시 해당 column 객체들의 `row`를 자동으로 할당합니다.
     - 가장 아래 객체가 `row=0`
     - 위로 갈수록 `+1`

## 파일 입출력

- 입력:
  - 이미지 파일: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`
  - LabelMe json: 이미지와 같은 파일명 기준으로 `<image_stem>.json`
- 저장:
  - 이미지마다 `<image_stem>.grid_labels.json` 파일을 생성/갱신합니다.
  - 기존 LabelMe 원본 JSON은 수정하지 않습니다.
  - 기존 LabelMe 객체는 원본 `points`/`shape_type`을 유지한 채 `col`, `row`만 추가 저장됩니다.
  - 수동 추가 객체는 `shape_type="point"`와 `points=[[x,y]]`로 저장됩니다.

## config.yml

기본 파일(`./config.yml`):

```yml
zoom_min: 0.5
zoom_max: 3.0
zoom_sensitivity: 0.15
```

- `zoom_min`, `zoom_max`: 휠 줌 배율 범위
- `zoom_sensitivity`: 휠 한 칸당 확대/축소 민감도
- 이미지를 바꾸면 줌 배율은 자동으로 `1.0`으로 초기화됩니다.

## 현재 1차 버전 포함 기능

- 폴더 기반 이미지 순회
- 기존 LabelMe 객체 중심점 자동 로드
- 점 객체 수동 추가
- 기존/수동 추가 점 객체 모두 `col`, `row` 편집
- 드래그 영역 선택 후 column 일괄 지정
- column 기준 row 자동 부여
- 이미지 전환 시 자동 저장 + 수동 저장 버튼
