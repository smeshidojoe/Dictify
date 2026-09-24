import multiprocessing

from dictify.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # the transcription worker process re-launches the frozen app
    main()
