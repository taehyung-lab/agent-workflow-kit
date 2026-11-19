"""수선소 명령줄 진입점."""
import json
import sys
import service
import storage
import validation

def main():
    try:
        args = sys.argv[1:]
        data = storage.read()
        if args == ['목록']:
            result = service.listing(data)
        elif len(args) == 2 and args[0] == '조회':
            result = service.find(data, validation.number(args[1]))
        elif len(args) == 3 and args[0] == '출고':
            result = service.receive(data, validation.number(args[1]), args[2])
            storage.write(data)
        else:
            raise ValueError('명령 또는 인수가 올바르지 않습니다')
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except json.JSONDecodeError:
        print(json.dumps({'오류': '자료 파일 형식이 올바르지 않습니다'}, ensure_ascii=False))
        return 1
    except OSError:
        print(json.dumps({'오류': '자료 파일을 읽거나 저장할 수 없습니다'}, ensure_ascii=False))
        return 1
    except ValueError as error:
        print(json.dumps({'오류': str(error)}, ensure_ascii=False))
        return 1

if __name__ == '__main__':
    sys.exit(main())
