MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']
DAYS = ['Su','Mo','Tu','We','Th','Fr','Sa']
START_YEAR = 23

import requests
from bs4 import BeautifulSoup
import pandas as pd
from icalendar import Calendar, Event
import unicodedata
import datetime

def get_tables(url):
    page = requests.get(url)
    soup = BeautifulSoup(page.content, "html.parser")
    tables = soup.find_all('table')

    return tables

def scrape_front():
    #### scraping front page to get role, name, and link
    URL_PREFIX = "https://amion.com/cgi-bin/ocs?File"

    url = "https://amion.com/cgi-bin/ocs?Lo=!94afe465pqcleq%26Enote=NoGT"
    # url = "https://amion.com/cgi-bin/ocs?Lo=!24a89140infihn%26Enote=NoGT"
    tables = get_tables(url)
    table = tables[0]
    data = []
    for row in table.find_all('tr',class_="grbg"):    
        columns = row.find_all('td')

        role = columns[0].text

        name_col = columns[2]
        name = name_col.text
        href = str(name_col).split('href=')[1].split(">")[0][9:-1]

        data.append((role,name,URL_PREFIX+href))

    df = pd.DataFrame(data,columns=["role","name","url"])
    return df

def format_dates(dates,year):

    # format the months
    months_list = []
    current_month = dates[0].split(" ")[1].split(" ")[0]
    for x in dates:
        x = x.replace("New year","January")
        t = x.split(" ")[-1]
        if t in MONTHS:
            current_month = t
        months_list += [current_month]

    # format days of the week
    num_weeks = int(np.ceil(len(dates)/7))
    day_week_list = (DAYS * num_weeks)[:len(dates)]

    # format the days
    days_list = [int(x.split(" ")[0]) for x in dates]

    # #fix the dec/jan bug
    if months_list[0] == "December" and months_list[-1] == "January": 
        year_list = []
        for m in months_list:
            if m == "December":
                year_list.append(year)
            else:
                year_list.append(year+1)
    else:
        year_list = [year] * len(months_list)

    datetime_list = [datetime.datetime(y,MONTHS.index(m)+1,d) for m, d, y in zip(months_list,days_list,year_list)]

    # else:
    #     datetime_list = [datetime.datetime(year,MONTHS.index(m)+1,d) for m, d in zip(months_list,days_list)]

    # datetime_list = [datetime.datetime(year,MONTHS.index(m)+1,d) for m, d in zip(months_list,days_list)]    

    return datetime_list, day_week_list

def parse_person_month(url):
    url = url.replace(" ", "%20")
    dfs = pd.read_html(url)

    # dates
    month_df = dfs[2]

    dates = []
    roles = []
    for i in range(0,len(month_df),2):
        t_dates, t_roles = month_df.loc[[i,i+1]].values
        dates += list(t_dates)
        roles += list(t_roles)


    year = int("20"+url.split("Mo=")[-1].split("-")[-1][:2])
    datetime_list, day_week_list = format_dates(dates,year)

    # blocks/roles
    rot_list = [unicodedata.normalize('NFKD', x).encode('ascii', 'ignore') for x in dfs[1].loc[1].values[:-1]]
    rot_list = np.array(list(set([x.decode("utf-8") for x in rot_list])))

    # fix the weird holiday block names
    for i,r in enumerate(rot_list):
        if "Holiday" in r:
            t = r.split("No Clinics")[1].strip().split("/")[-1]
            if t[1].isdigit():
                t = t[2:]
            else:
                t = t[1:]
            rot_list[i] = t

    block_list, role_list  = format_block_roles(roles,rot_list)

    return datetime_list, day_week_list, block_list, role_list

def parse_person_urls(url_temp):
    current_month = datetime.datetime.now().month
    current_year = datetime.datetime.now().year - 2000

    l = 12 - current_month
    months_in_year = [current_month+i for i in range(l+1)]

    if current_year == START_YEAR:
        remaining_years = [current_year, current_year+1]
        remaining_months = [months_in_year,list(range(1,7))]
    else:
        remaining_years = [current_year]
        remaining_months = [months_in_year]

    urls = []
    for i in range(len(remaining_years)):
        for m, y in zip(remaining_months[i],repeat(remaining_years[i],len(remaining_months[i]))):
            urls.append(url_temp[:-17]+str(m)+"-"+str(y)+"&amp")

    return urls

def parse_person(url_temp,name):
    urls = parse_person_urls(url_temp)
    dfs = []
    for url in urls:
        print(url)
        data = parse_person_month(url)
        df = pd.DataFrame(data).transpose()
        dfs.append(df)

    final_df = pd.concat(dfs)
    final_df.columns = ['date','day','block','role']
    final_df['name'] = name
    final_df = final_df.sort_values("date")
    final_df = final_df.reset_index(drop=True)
    # drop the last row to get rid of extra dec day
    final_df = final_df.drop(final_df.index[-1])

    final_df = final_df.drop_duplicates()

    final_df['off'] = final_df.apply(lambda x: day_off(x),axis=1)

    return final_df

def format_block_roles(roles,rot_list):
    #reformat to include date, day of week, month, year, block, role
    block_list = []
    role_list = []
    for r in roles:
        if r!=r:
            r = ""

        r = unicodedata.normalize('NFKD', r).encode('ascii', 'ignore')
        r = r.decode("utf-8") 
        block = rot_list[[x in r for x in rot_list]]
        if len(block) == 0:
            block = "EMPTY"
        else:
            block = block[0]

        block_list.append(block)
        role = r.replace(block,"")
        if role == "":
            role = block
        role_list.append(role)

    return block_list, role_list


def day_off(x):
    if "ASE:" in x['block'] or "ELECT:" in x['block'] or "ACR" in x['block']:
         if x['day'] in ['Su','Sa'] and "Coverage" not in x['role'] and "Weekend" not in x['role']:
            return True

    if "off" in x['role'].lower():
        return True

    if x['block'] == "VACA":
        return True

    if "Holiday BLOCK" in x["role"]:
        return True

    return False



# def parse_ics(file_name):
#     g = open(file_name,'rb')
#     gcal = Calendar.from_ical(g.read())
#     components = []
#     i = 0
#     for component in gcal.walk():
#         components.append(component)
#         i +=1
#         # if True:
#         if component.name == "VEVENT":
#             shift_name = component.get('summary')
#             date_start = component.get('DTSTART').dt
#             date_end = component.get("DTEND").dt
#             print(shift_name,date_start,date_end)
#         else:
#             print(i)
