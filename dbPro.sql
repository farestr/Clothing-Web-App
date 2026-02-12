

DROP DATABASE IF EXISTS clothing_store_db;
CREATE DATABASE clothing_store_db;
USE clothing_store_db;


CREATE TABLE User (
  UserID INT AUTO_INCREMENT PRIMARY KEY,
  Password VARCHAR(100) NOT NULL,
  Name VARCHAR(100) NOT NULL,
  Address VARCHAR(200),
  Email VARCHAR(100) UNIQUE,
  Phone_Number VARCHAR(20),
  Role ENUM('Customer','Employee','Admin','Supplier') NOT NULL DEFAULT 'Customer'
);

CREATE TABLE Customer (
  UserID INT PRIMARY KEY,
  FOREIGN KEY (UserID) REFERENCES User(UserID)
);


CREATE TABLE Place (
  PlaceID INT AUTO_INCREMENT PRIMARY KEY,
  Type ENUM('Warehouse','Store'),
  Location VARCHAR(200),
  Governate VARCHAR(100),
  City VARCHAR(100),
  Street VARCHAR(100)
);

CREATE TABLE Employee (
  UserID INT PRIMARY KEY,
  Position VARCHAR(100),
  Salary DECIMAL(10,2),
  PlaceID INT,
  FOREIGN KEY (UserID) REFERENCES User(UserID),
  FOREIGN KEY (PlaceID) REFERENCES Place(PlaceID)
);


CREATE TABLE Supplier (
  SupplierID INT AUTO_INCREMENT PRIMARY KEY,
  Name VARCHAR(100) NOT NULL,
  Email VARCHAR(100),
  Phone VARCHAR(20),
  Address VARCHAR(200),
  UserID INT UNIQUE,
  FOREIGN KEY (UserID) REFERENCES User(UserID)
);

CREATE TABLE Model (
  ModelID INT AUTO_INCREMENT PRIMARY KEY,
  ModelNumber VARCHAR(50) NOT NULL,
  Name VARCHAR(100),
  Description VARCHAR(300),
  Gender ENUM('Male','Female','Both'),
  Price DECIMAL(10,2),
  Sell_Price DECIMAL(10,2),
  Profit DECIMAL(10,2),
  Item_Image VARCHAR(200),
  SupplierID INT,
  FOREIGN KEY (SupplierID) REFERENCES Supplier(SupplierID)
);

CREATE TABLE Item (
  ItemID INT AUTO_INCREMENT PRIMARY KEY,
  ModelID INT NOT NULL,
  Size VARCHAR(10),
  Color VARCHAR(30),
  FOREIGN KEY (ModelID) REFERENCES Model(ModelID)
);


CREATE TABLE Inventory (
  PlaceID INT,
  ItemID INT,
  Quantity INT DEFAULT 0,
  ReservedQuantity INT DEFAULT 0,
  PRIMARY KEY (PlaceID, ItemID),
  FOREIGN KEY (PlaceID) REFERENCES Place(PlaceID),
  FOREIGN KEY (ItemID) REFERENCES Item(ItemID)
);


CREATE TABLE Invoice (
  InvoiceID INT AUTO_INCREMENT PRIMARY KEY,
  CustomerID INT NOT NULL,
  EmployeeID INT NULL,
  TotalAmount DECIMAL(10,2) NOT NULL,
  Date DATE,
  Status ENUM('Pending','Accepted','Prepared','Completed') DEFAULT 'Pending',
  FOREIGN KEY (CustomerID) REFERENCES Customer(UserID),
  FOREIGN KEY (EmployeeID) REFERENCES Employee(UserID)
);

CREATE TABLE Orders (
  OrderID INT AUTO_INCREMENT PRIMARY KEY,
  InvoiceID INT NOT NULL,
  ItemID INT NOT NULL,
  Quantity INT NOT NULL,
  Amount DECIMAL(10,2) NOT NULL,
  FOREIGN KEY (InvoiceID) REFERENCES Invoice(InvoiceID),
  FOREIGN KEY (ItemID) REFERENCES Item(ItemID)
);


CREATE TABLE SupplyOrder (
  SupplyOrderID INT AUTO_INCREMENT PRIMARY KEY,
  SupplierID INT NOT NULL,
  PlaceID INT NOT NULL,
  CreatedByUserID INT NOT NULL,
  DeliveredBySupplierID INT NULL,
  TotalAmount DECIMAL(10,2) DEFAULT 0,
  Date DATE NOT NULL,
  Status ENUM('Pending','Delivered','Cancelled') DEFAULT 'Pending',
  FOREIGN KEY (SupplierID) REFERENCES Supplier(SupplierID),
  FOREIGN KEY (PlaceID) REFERENCES Place(PlaceID),
  FOREIGN KEY (CreatedByUserID) REFERENCES User(UserID),
  FOREIGN KEY (DeliveredBySupplierID) REFERENCES Supplier(SupplierID)
);

CREATE TABLE SupplyOrderLine (
  SupplyOrderLineID INT AUTO_INCREMENT PRIMARY KEY,
  SupplyOrderID INT NOT NULL,
  ItemID INT NOT NULL,
  Quantity INT NOT NULL,
  UnitCost DECIMAL(10,2) NOT NULL,
  Amount DECIMAL(10,2) NOT NULL,
  FOREIGN KEY (SupplyOrderID) REFERENCES SupplyOrder(SupplyOrderID),
  FOREIGN KEY (ItemID) REFERENCES Item(ItemID)
);



INSERT INTO Place (Type, Location, Governate, City, Street)
VALUES
('Store','Downtown Store','Ramallah','Ramallah','Main St 1'),
('Warehouse','Central Warehouse','Ramallah','Ramallah','Warehouse Rd 2');

INSERT INTO User (Name, Email, Password, Role) VALUES
('Alice Customer','alice@example.com','password','Customer'),
('Bob Customer','bob@example.com','password','Customer'),
('Charlie Admin','charlie@example.com','password','Admin');

INSERT INTO Customer (UserID) VALUES (1),(2);

INSERT INTO User (Name, Email, Password, Role) VALUES
('Fashion Wholesale Login','contact@fashionwholesale.com','password','Supplier'),
('Global Textiles Login','sales@globaltextiles.com','password','Supplier');

INSERT INTO Supplier (Name, Email, Phone, Address, UserID) VALUES
('Fashion Wholesale Co.','contact@fashionwholesale.com','+97012345678','Ramallah, Palestine', 4),
('Global Textiles','sales@globaltextiles.com','+97098765432','Nablus, Palestine', 5);

INSERT INTO Model (ModelNumber, Name, Description, Gender, Price, Sell_Price, Profit, Item_Image, SupplierID) VALUES
('M001','Blue Shirt','Slim fit blue shirt','Male',25.00,40.00,15.00,'blue_shirt.png', 1),
('M002','Red Dress','Elegant red dress','Female',50.00,80.00,30.00,'red_dress.png', 2);

INSERT INTO Item (ModelID, Size, Color) VALUES
(1,'M','Blue'),
(1,'L','Blue'),
(2,'S','Red'),
(2,'M','Red');

INSERT INTO Inventory (PlaceID, ItemID, Quantity, ReservedQuantity) VALUES
(1,1,10,0),
(1,2,5,0),
(1,3,8,0),
(1,4,4,0),
(2,1,50,0),
(2,2,50,0),
(2,3,30,0),
(2,4,30,0);


INSERT INTO Invoice (CustomerID, EmployeeID, TotalAmount, Date, Status) VALUES
(1,NULL,120.00,'2026-01-18','Pending'),
(2,NULL,80.00,'2026-01-18','Pending');

INSERT INTO Orders (InvoiceID, ItemID, Quantity, Amount) VALUES
(1,1,2,80.00),
(1,3,1,40.00),
(2,4,1,80.00);

INSERT INTO SupplyOrder (SupplierID, PlaceID, CreatedByUserID, DeliveredBySupplierID, TotalAmount, Date, Status)
VALUES (1, 2, 3, NULL, 0, '2026-01-18', 'Pending');

INSERT INTO SupplyOrderLine (SupplyOrderID, ItemID, Quantity, UnitCost, Amount) VALUES
(1, 1, 20, 18.00, 360.00),
(1, 2, 10, 18.00, 180.00);

UPDATE SupplyOrder
SET TotalAmount = 540.00
WHERE SupplyOrderID = 1;

SELECT * FROM User;
SELECT * FROM Supplier;
SELECT * FROM SupplyOrder;
SELECT * FROM SupplyOrderLine;
