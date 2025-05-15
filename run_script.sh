#!/bin/bash

CMD1="$REPOPATH/build/bin/llama-server -m $MODELPATH"
CMD2="~/.venv/llama.cpp/bin/python $REPOPATH/_webdemo/app.py"


# export REPOPATH='/home/lsm0729/Repo/llama.cpp'
# export MODELPATH='/home/lsm0729/Repo/llama.cpp/exaone.gguf'

LOG_FILE="/dev/null"

run_commands() {
    echo "백그라운드에서 다음 명령어들을 실행합니다 (로그 숨김):"
    echo "1. $CMD1"
    nohup sh -c "$CMD1" > "$LOG_FILE" 2>&1 &
    if [ $? -eq 0 ]; then
        echo "  명령어 1이 백그라운드에서 실행되었습니다."
    else
        echo "  명령어 1 실행에 실패했습니다."
    fi

    echo "2. $CMD2"
    # CMD2의 ~경로가 올바르게 확장되도록 eval 사용 또는 직접 실행
    # nohup eval "$CMD2" > "$LOG_FILE" 2>&1 &
    # 또는 더 안전하게:
    expanded_cmd2=$(eval echo $CMD2) # ~ 확장
    nohup sh -c "$expanded_cmd2" > "$LOG_FILE" 2>&1 &
    if [ $? -eq 0 ]; then
        echo "  명령어 2가 백그라운드에서 실행되었습니다."
    else
        echo "  명령어 2 실행에 실패했습니다."
    fi
    echo "PID는 'pgrep -f \"부분_명령어\"' 등으로 확인할 수 있습니다."
}

stop_processes_on_port() {
    local port=$1
    echo "포트 $port 에서 LISTEN 중인 TCP 프로세스를 찾아 종료합니다..."
    pids_output=$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null)

    if [ -n "$pids_output" ]; then
        echo "$pids_output" | while IFS= read -r pid; do
            if [ -n "$pid" ]; then # 빈 줄 방지
                echo "  PID $pid (포트 $port 사용) 프로세스를 강제 종료합니다 (kill -9 $pid)."
                if kill -9 "$pid" 2>/dev/null; then
                    echo "    PID $pid 종료 성공."
                else
                    echo "    PID $pid 종료 실패 (이미 종료되었거나 권한 문제일 수 있습니다)."
                fi
            fi
        done
    else
        echo "  포트 $port 에서 LISTEN 중인 TCP 프로세스를 찾을 수 없습니다."
    fi
}

stop_all_commands() {
    stop_processes_on_port 8080
    stop_processes_on_port 5000
    echo "지정된 포트의 프로세스들에 대한 중지 작업이 완료되었습니다."
}

show_menu() {
    echo ""
    echo "스크립트 작업을 선택하세요:"
    echo "  run   - 백그라운드 명령어 실행"
    echo "  stop  - 지정된 포트(8080, 5000)의 프로세스 중지"
    echo "  exit  - 스크립트 종료"
    echo -n "선택: "
}

# --- 메인 루프 ---
while true; do
    show_menu
    read -r choice

    case "$choice" in
        run)
            run_commands
            ;;
        stop)
            # lsof 명령어 존재 확인
            if ! command -v lsof &> /dev/null; then
                echo "오류: 'lsof' 명령어를 찾을 수 없습니다. 'stop' 기능을 사용하려면 설치해야 합니다."
                echo "      (예: sudo apt-get install lsof  또는  sudo yum install lsof)"
            else
                stop_all_commands
            fi
            ;;
        exit)
            echo "스크립트를 종료합니다."
            exit 0
            ;;
        *)
            echo "잘못된 선택입니다. 'run', 'stop', 'exit' 중 하나를 입력하세요."
            ;;
    esac
done
