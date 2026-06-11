def main():
    while True:
        print("\nOptions:")
        print("e. Exit")
        choice = input("Select an option [e]: ").strip().lower()

        if choice == "e":
            break
        else:
            print("Unknown option.")


if __name__ == "__main__":
    main()
