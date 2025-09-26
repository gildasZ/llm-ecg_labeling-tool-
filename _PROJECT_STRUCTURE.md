## Project Structure: 

```text
Label-V04-Trading-Assistant/
├── _Testing_Codes_Folder/
│   ├── __pycache__/
│   │   ├── __init__.cpython-310.pyc
│   │   ├── __init__.cpython-312.pyc
│   │   ├── utils_custom.cpython-310.pyc
│   │   └── utils_custom.cpython-312.pyc
│   ├── Splitting_Data_to_Files/
│   │   └── Splitting_Data_to_Files.ipynb
│   ├── 1 D 5 mins AAPL Historical Data.png
│   ├── 1D_5mins_aapl_historical_data.csv
│   ├── __init__.py
│   ├── _random.py
│   ├── dummy_python_file.py
│   ├── Figure_1.png
│   ├── For_Lab_Server_Download_Polygon_io_data.py
│   ├── Test_001_Polygon_io.py
│   ├── Test_001_V02_Polygon_io.py
│   ├── Test_001_V03_Polygon_io.py
│   ├── Test_001_V04_Polygon_io_Add_Indic.py
│   ├── Test_002_IBK_API.py
│   ├── Test_003_001_Plotting.py
│   ├── Test_003_IBK_API_Long_Request.py
│   ├── Test_003_IBK_API_Long_Request_functions.py
│   ├── Test_003_V2_IBK_API_Long_Request_functions.py
│   ├── Test_004_cryptocompare.py
│   └── utils_custom.py
├── default_media_files/
│   ├── models_to_use/
│   │   ├── _Instructions.txt
│   │   ├── _Models_List - Copy.csv
│   │   ├── _Models_List - Real One.csv
│   │   ├── _Models_List.csv
│   │   ├── BiGRUWithAttention_epoch_1072.pth
│   │   ├── BiGRUWithAttention_epoch_1163.pth
│   │   ├── BiGRUWithAttention_epoch_1192.pth
│   │   ├── BiGRUWithAttention_epoch_129.pth
│   │   ├── BiGRUWithAttention_epoch_88.pth
│   │   ├── Classif_GRU_Model_epoch_15616.pth
│   │   ├── Classif_GRU_Model_epoch_15616_alt.pth
│   │   ├── Classif_GRU_Model_epoch_15617.pth
│   │   └── Classif_GRU_Model_epoch_15895.pth
│   └── Raw_Time_Series_Data/ (empty)
├── home/
│   ├── __pycache__/
│   │   ├── __init__.cpython-312.pyc
│   │   ├── admin.cpython-312.pyc
│   │   ├── apps.cpython-312.pyc
│   │   ├── consumers.cpython-312.pyc
│   │   ├── middleware.cpython-312.pyc
│   │   ├── models.cpython-312.pyc
│   │   ├── routing.cpython-312.pyc
│   │   ├── urls.cpython-312.pyc
│   │   ├── utils.cpython-312.pyc
│   │   └── views.cpython-312.pyc
│   ├── assets/ (empty)
│   ├── dash_apps/
│   │   └── finished_apps/
│   │       ├── __pycache__/
│   │       │   └── ... (contents pruned at max_depth=4)
│   │       ├── Delete_dummy_HTML.html
│   │       ├── display_ecg_graph.py
│   │       └── display_ecg_graph_20250422_Abandonned.py
│   ├── migrations/
│   │   ├── __pycache__/
│   │   │   └── __init__.cpython-312.pyc
│   │   └── __init__.py
│   ├── templates/
│   │   └── home/
│   │       ├── login.html
│   │       ├── logout.html
│   │       ├── register.html
│   │       └── welcome.html
│   ├── __init__.py
│   ├── _random.py
│   ├── admin.py
│   ├── apps.py
│   ├── consumers.py
│   ├── consumers_20250422_Abandonned.py
│   ├── middleware.py
│   ├── models.py
│   ├── routing.py
│   ├── tests.py
│   ├── urls.py
│   ├── utils.py
│   └── views.py
├── label_V04/
│   ├── __pycache__/
│   │   ├── __init__.cpython-312.pyc
│   │   ├── asgi.cpython-312.pyc
│   │   ├── settings.cpython-312.pyc
│   │   └── urls.cpython-312.pyc
│   ├── static/
│   │   └── channels/
│   │       └── js/
│   │           └── ... (contents pruned at max_depth=4)
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── media/ (empty)
├── staticfiles_collected/
│   ├── admin/
│   │   ├── css/
│   │   │   ├── vendor/
│   │   │   │   └── ... (contents pruned at max_depth=4)
│   │   │   ├── autocomplete.css
│   │   │   ├── base.css
│   │   │   ├── changelists.css
│   │   │   ├── dark_mode.css
│   │   │   ├── dashboard.css
│   │   │   ├── forms.css
│   │   │   ├── login.css
│   │   │   ├── nav_sidebar.css
│   │   │   ├── responsive.css
│   │   │   ├── responsive_rtl.css
│   │   │   ├── rtl.css
│   │   │   └── widgets.css
│   │   ├── img/
│   │   │   ├── gis/
│   │   │   │   └── ... (contents pruned at max_depth=4)
│   │   │   ├── calendar-icons.svg
│   │   │   ├── icon-addlink.svg
│   │   │   ├── icon-alert.svg
│   │   │   ├── icon-calendar.svg
│   │   │   ├── icon-changelink.svg
│   │   │   ├── icon-clock.svg
│   │   │   ├── icon-deletelink.svg
│   │   │   ├── icon-hidelink.svg
│   │   │   ├── icon-no.svg
│   │   │   ├── icon-unknown-alt.svg
│   │   │   ├── icon-unknown.svg
│   │   │   ├── icon-viewlink.svg
│   │   │   ├── icon-yes.svg
│   │   │   ├── inline-delete.svg
│   │   │   ├── LICENSE
│   │   │   ├── README.txt
│   │   │   ├── search.svg
│   │   │   ├── selector-icons.svg
│   │   │   ├── sorting-icons.svg
│   │   │   ├── tooltag-add.svg
│   │   │   └── tooltag-arrowright.svg
│   │   └── js/
│   │       ├── admin/
│   │       │   └── ... (contents pruned at max_depth=4)
│   │       ├── vendor/
│   │       │   └── ... (contents pruned at max_depth=4)
│   │       ├── actions.js
│   │       ├── autocomplete.js
│   │       ├── calendar.js
│   │       ├── cancel.js
│   │       ├── change_form.js
│   │       ├── collapse.js
│   │       ├── core.js
│   │       ├── filters.js
│   │       ├── inlines.js
│   │       ├── jquery.init.js
│   │       ├── nav_sidebar.js
│   │       ├── popup_response.js
│   │       ├── prepopulate.js
│   │       ├── prepopulate_init.js
│   │       ├── SelectBox.js
│   │       ├── SelectFilter2.js
│   │       ├── theme.js
│   │       └── urlify.js
│   ├── channels/
│   │   └── js/
│   │       └── websocketbridge.js
│   ├── dash/
│   │   └── component/
│   │       ├── dash/
│   │       │   └── ... (contents pruned at max_depth=4)
│   │       ├── dash_bootstrap_components/
│   │       │   └── ... (contents pruned at max_depth=4)
│   │       ├── dpd_components/
│   │       │   └── ... (contents pruned at max_depth=4)
│   │       └── dpd_static_support/
│   │           └── ... (contents pruned at max_depth=4)
│   ├── dpd/
│   │   └── assets/
│   │       └── home/
│   └── dpd_static_support/
│       ├── css/
│       │   ├── bootstrap-grid.css
│       │   ├── bootstrap-grid.min.css
│       │   ├── bootstrap-reboot.css
│       │   ├── bootstrap-reboot.min.css
│       │   ├── bootstrap.css
│       │   └── bootstrap.min.css
│       └── js/
│           ├── bootstrap.bundle.js
│           ├── bootstrap.bundle.min.js
│           ├── bootstrap.js
│           ├── bootstrap.min.js
│           ├── jquery-3.3.1.js
│           ├── jquery-3.3.1.min.js
│           ├── popper.js
│           ├── popper.min.js
│           ├── tooltip.js
│           └── tooltip.min.js
├── templates/
│   ├── partials/
│   │   ├── Bodypart/
│   │   │   ├── _bodypart.html
│   │   │   ├── _bodypart_dropdown.html
│   │   │   ├── _bodypart_dropdown_20250415_Checkpoint_No_Upload.html
│   │   │   ├── _bodypart_ECGgraph.html
│   │   │   ├── _bodypart_labeled_patterns.html
│   │   │   ├── _bodypart_statements.html
│   │   │   └── _bodypart_textual_explanation.html
│   │   ├── Footer/
│   │   │   └── _footer.html
│   │   ├── Sidebar/
│   │   │   ├── _sidebar.html
│   │   │   ├── _sidebar_section_1.html
│   │   │   ├── _sidebar_section_2.html
│   │   │   └── _sidebar_section_3.html
│   │   └── Topbar/
│   │       └── _topbar.html
│   ├── base.html
│   └── index.html
├── _get_code_state.py
├── ALL_MODELS.zip
├── Check--Notes for commands.txt
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh
├── list_structure.py
├── manage.py
├── Pipfile
├── Pipfile.lock
├── README copy.md
├── README.md
├── requirements.txt
└── Testing_existence.csv
```

*Structure listing generated with `max_depth=4`.*
