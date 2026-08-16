def main() -> None:
    from tiles_survive_automation import config

    config.ensure_data_dirs()
    print("Tiles Survive Automation — skeleton OK")


if __name__ == "__main__":
    main()
