
# Thường để crawl từ các trang thương mại điên tử như Shopee, Tiki, hay Lazada ta có thể 
# gọi thẳng api để lấy được kết quả nhưng hiện nay shopee đã bảo mật api này không cho chúng ta tự
# do truy cập nữa do đó chúng ta phải sử dùng các automation browser như selenium để có thể crawl được dữ liệu 
# mong muốn!

# Ở đây sử dụng undetected_chromedriver một bản folk của selenium bởi vì shopee có kiểm tra bot nên selenium thông thường không
# thể sử dụng được. Dữ liệu sẽ được bắt khi web client goi XHR tới server của shopee, code sẽ tự điều khiển để những trang cần thiết để
# lấy hết danh sách sản phẩm của 1 shop trên shopee.

# Ví dụ dưới đây sẽ lấy các sản phẩm của shop the_deme, bao gồm 2 loại: thông thường và bán hết.
# Link shop: https://shopee.vn/the_deme
# Tổng sản phẩm lấy được: 179 trong đó 128 bình thường, 51 bán hết.
# Link video: https://youtu.be/k8FysKa7T4g
# Phải đăng nhập shopee để tránh bị đẩy tơi trang đăng nhập thường xuyên.

import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse, parse_qs
import json
from time import sleep
from pprint import pformat
import threading
import os
import pandas as pd

shop_id = 'the_deme'
login_url = 'https://shopee.vn/buyer/login?next=https%3A%2F%2Fshopee.vn%2Froman.official%3Fpage%3D01'
shop_url = 'https://shopee.vn/{}#product_list'.format(shop_id)


shop_base_api = "https://shopee.vn/api/v4/shop/get_shop_base"
shop_item_rcmd_api = "https://shopee.vn/api/v4/shop/rcmd_items"
shop_sold_out_api = "https://shopee.vn/api/v4/shop/search_items?filter_sold_out"

items_per_page = 30

options = uc.ChromeOptions()

options.user_data_dir="./temp/profile"

driver = uc.Chrome(version_main=121, options=options,enable_cdp_events=True)


shopCollectDic = {
    "recommended": {},
    "soldOut": {}
}

collectInfo = {
    'totalItems': 0,
    'totalRecommendedItems': 0,
    'totalSoldOutItems' : 0
}


def getXHRdata(eventdata):
    resp_url = eventdata["params"]["response"]["url"]

    if not resp_url.startswith("https://shopee.vn/api/v4/shop/"):
         return
    
    request_id = eventdata["params"]["requestId"]
    data =  driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
    if resp_url.startswith(shop_base_api):
      covertBaseShopInfo(data['body'])
    
    # shop recommended items
    if resp_url.startswith(shop_item_rcmd_api):
       
       dat = json.loads(data['body'])['data']
       items = dat['items']
       offSet =  int(parse_qs(urlparse(resp_url).query)['offset'][0])
       offSet = offSet // items_per_page
       # add to collect dic
       shopCollectDic['recommended'][offSet] = items

       if collectInfo['totalRecommendedItems'] == 0:
           print("totalRecommendedItems:", dat['total'])

       collectInfo['totalRecommendedItems'] = dat['total']
       

  
    # shope sold out items
    if resp_url.startswith(shop_sold_out_api):
       dat = json.loads(data['body'])
       items = dat['items']
       offSet =  int(parse_qs(urlparse(resp_url).query)['offset'][0])
       offSet = offSet // items_per_page

       if collectInfo['totalSoldOutItems'] == 0:
           print("totalSoldOutItems:", dat['total_count'])

       collectInfo['totalSoldOutItems']  = dat['total_count']

       shopCollectDic['soldOut'][offSet] = items
        # add to collect dic

       assert collectInfo['totalRecommendedItems'] + collectInfo['totalSoldOutItems'] == collectInfo['totalItems'],  \
         'should totalRecommendedItems:{} + totalSoldOutItems:{} = totalItems{}'\
          .format(collectInfo['totalRecommendedItems'],collectInfo['totalSoldOutItems'],collectInfo['totalItems'])

# 30 items per page
def calPageCount(itemCount):

    pageCount = itemCount // items_per_page
    if (itemCount % items_per_page) > 0:
        pageCount+=1
    return pageCount


def onPageNavigated(eventdata):
    resp_url = eventdata["params"]["frame"]["url"]
    if resp_url == 'about:blank':
        return

    print("Navigate to:" + resp_url)

def covertBaseShopInfo(rawdata):
   rawdata = json.loads(rawdata)   
   name = rawdata['data']['name']
   description = rawdata['data']['description']
   itemCount = rawdata['data']['item_count']
   print(pformat({
       'name': name,
       'description':description,
       'itemCount': itemCount
   }))

   collectInfo['totalItems'] = itemCount

   # start collect shop items
   collectorThread = threading.Thread(target=startCollectShopItems, args=(itemCount,))
   collectorThread.start()


def startCollectShopItems(itemCount):
    pageCount = calPageCount(itemCount)

    print("Calculate number of pages to get data:",pageCount)
    
    # collect recommended item
    for i in range(pageCount):
        # stop, we had reach last page, time to collect sold out
        if collectInfo['totalRecommendedItems'] != 0 and (i * items_per_page )> collectInfo['totalRecommendedItems']:
           break

        # If the condition is not satisfied, wait for some time
        collectInPage(i)
        while True:
            # Check the condition
           if i in shopCollectDic['recommended'] and shopCollectDic['recommended'][i] is not None:
            print("Got recommended items from page:",i)
            
            break  # Exit the loop if the condition is satisfied
                   
           sleep(1)  # Wait for 1 second (adjust as needed)
    
  

    # wait for totalSoldOutItems have value 
    while True:
      if collectInfo['totalSoldOutItems'] != 0:
        break
      sleep(1)
       
    slideCount = calPageCount(collectInfo['totalSoldOutItems'])

    print("Calculate number of slide to get sold out items:",slideCount)

    # collect recommended item
    for i in range(slideCount):
        collectSoldOut()
        while True:
            # Check the condition
           if i in shopCollectDic['soldOut'] and shopCollectDic['soldOut'][i] is not None:
            print("Got sold out items from slide:",i)
        
            break  # Exit the loop if the condition is satisfied
                   
           sleep(1)  # Wait for 1 second (adjust as needed)

    print("Everything complete !!!")

    concreteData()

# sold out items appear at the end of the number of recommened items page
def collectSoldOut():
    # Calculate the scroll height of the page
    scroll_height = driver.execute_script("return document.body.scrollHeight")
    # Calculate the target scroll position (90% of the scroll height)
    target_scroll_position = scroll_height * 0.9
    # Scroll the page to the target position
    driver.execute_script("window.scrollTo(0, arguments[0]);", target_scroll_position)

    button_element = driver.find_element("xpath","//div[@class='shop-sold-out-see-more']//button[@class='shopee-button-outline']")
    # Click the first button found (you can iterate over 'buttons' if there are multiple matching buttons)
    if button_element:
        print("Send click to more button")
        button_element.click()


def collectInPage(pageIndex):

    if pageIndex == 0:
        sleep(5)

    # we just change page to receive data for network api event
    # Define the class name and text content to search for
    class_name = "shopee-button-no-outline"
    content = pageIndex + 1
    # Construct an XPath expression to find elements with the specified class name and text content
    xpath_expression = f"//button[contains(@class, '{class_name}') and text()='{content}']"
    
    # Find elements matching the XPath expression
    try:
        button = driver.find_element('xpath',xpath_expression)
        if button:
          print("Send click to button:",pageIndex)
          button.click()

    except:
        return


# extract needed data and save it
def concreteData():
 
   folder_path = 'data'
   # Check if the folder exists, create it if it doesn't
   if not os.path.exists(folder_path):
     os.makedirs(folder_path)

   allItems = []
    
   [allItems.extend(subItems) for subItems in  shopCollectDic['recommended'].values()]
   [allItems.extend(subItems) for subItems in  shopCollectDic['soldOut'].values()]

   df = pd.DataFrame()

   for item in allItems:
      
      if not 'item_basic' in item:
          # normal item
          row_df = pd.DataFrame({
             'name': [item['name']],
             'historical_sold': [item['historical_sold']],
             'price': [item['price']],
             'rating_star': [item['item_rating']['rating_star']],
             'image': ['https://down-vn.img.susercontent.com/file/{}_tn'.format(item['image'])],
             'status': 'normal'
           })   
      else:
          # sold out item
          row_df = pd.DataFrame({
             'name': [item['item_basic']['name']],
             'historical_sold':  [item['item_basic']['historical_sold']],
             'price':  [item['item_basic']['price']],
             'rating_star':  [item['item_basic']['item_rating']['rating_star']],
             'image': ['https://down-vn.img.susercontent.com/file/{}_tn'.format(item['item_basic']['image'])],
             'status': 'sold out'
          })   

      df = pd.concat([df,row_df])


   df = df.reset_index(drop=True)   
   df.to_csv('./data/{}.csv'.format(shop_id),encoding='utf-8-sig')

   print("Saved data !!!")
     
driver.add_cdp_listener("Network.responseReceived", getXHRdata)
driver.add_cdp_listener("Page.frameNavigated", onPageNavigated)
driver.get(shop_url)

# equit
input("Press any key to exit ! \n")
driver.quit()