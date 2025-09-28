import argparse, json
from analyzer import analyze_contract

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--token", required=True)
    p.add_argument("--chain-id", type=int, default=1)
    p.add_argument("--block-tag")
    args = p.parse_args()
    out = analyze_contract(args.token, args.chain_id, args.block_tag)
    print(json.dumps(out.model_dump(), indent=2))

if __name__ == "__main__":
    main()
