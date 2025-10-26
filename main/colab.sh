!pip install xlsxwriter
!git clone https://github.com/DerivedFunction/acct-cik
!cp -rf acct-cik/main/* .

!cd acct-cik && git pull && cd ..
!cp -rf acct-cik/main/* .